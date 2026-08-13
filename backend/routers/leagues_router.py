"""League operations router — ported from the standalone `disc-leauge-ops`
FastAPI app into an APIRouter that plugs into the Ace Chasers backend.

Key adaptations vs the original standalone app:
  - Auth uses the existing Firebase-based `get_current_user` from deps.py;
    the old Emergent OAuth cookie-session endpoints are removed. A thin
    compat wrapper `get_current_user_compat` maps the Firebase uid onto the
    `User(user_id=...)` shape the league code expects.
  - Object storage swapped from Emergent object storage to Cloudinary.
    `put_object` / `get_object` are compat shims that return a dict shaped
    like the old Emergent storage response so route handlers stay untouched.
  - The module-level `app = FastAPI()` and `startup` event are removed —
    startup is owned by the main Ace Chasers server.
  - The Mongo client is reused via `deps.get_db()`.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Header, Query, Response, Cookie, Request
from fastapi.responses import JSONResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import asyncio
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Dict, Any
import uuid
import base64
import requests
from datetime import datetime, timezone, timedelta

# Reuse the shared MongoDB connection so this router doesn't open a second
# client. `db.get_db()` returns the same DB instance the rest of the app uses.
from firebase_auth import get_current_user as _fb_get_current_user  # noqa: E402
from db import get_db  # noqa: E402
import cloud_storage  # noqa: E402

db = get_db()

APP_NAME = os.environ.get('APP_NAME', 'acechasers')

api_router = APIRouter()

logger = logging.getLogger(__name__)

# ============= STORAGE (Cloudinary-backed compat shims) =============
# The original league app spoke to Emergent object storage via HTTP with
# `put_object(path, bytes, content_type)` -> dict, and served bytes back
# via `get_object(path)` -> (bytes, content_type). We replace both with
# Cloudinary uploads. Callers still get a dict; the `secure_url` field
# points at Cloudinary and can be used verbatim in the frontend.


def _looks_like_video(content_type: str, path: str) -> bool:
    ct = (content_type or "").lower()
    if ct.startswith("video/"):
        return True
    return path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))


def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload `data` to Cloudinary under a stable folder derived from `path`.

    Returns a dict compatible with the old Emergent-storage response shape:
      {"path": "<original path>", "url": "<cloudinary secure_url>",
       "content_type": "...", "size": <bytes>}
    """
    resource_type = "video" if _looks_like_video(content_type, path) else "image"
    folder = f"acechasers-leagues/{Path(path).parent.as_posix()}".rstrip("/")
    result = cloud_storage.upload_bytes(
        data,
        resource_type=resource_type,
        folder=folder,
        public_id=Path(path).stem,
    )
    url = result.get("secure_url") or result.get("url")
    return {
        "path": path,
        "url": url,
        "content_type": content_type,
        "size": len(data),
        "cloudinary_public_id": result.get("public_id"),
    }


def get_object(path: str):
    """Kept for source-compat. New code should embed Cloudinary URLs
    directly on the frontend; this fetches through if a caller still needs
    raw bytes (rare)."""
    # The Cloudinary URL is stored on the referring document; if a route
    # ends up calling this, we have no mapping table so we raise.
    raise HTTPException(
        status_code=404,
        detail=(
            "Legacy /files/{path} route is deprecated in the merged build. "
            "Use the `url` returned by /files/upload directly."
        ),
    )


# ============= AUTH (Firebase bridge) =============
# `User` is defined below in the MODELS section; the shape there is what
# the rest of this file relies on. We use it via forward reference here.


async def _upsert_league_user(uid: str, fb_user: dict) -> dict:
    """Ensure a `users` row exists for this Firebase uid so the rest of the
    league code — which reads/writes `db.users` on `user_id` — has a record
    to hang data off. Non-destructive; only fills missing fields."""
    # Ace Chasers users collection is keyed by `uid` (unique index). The
    # league code expects a `user_id` field, so we map uid<->user_id and
    # upsert on uid to avoid duplicate-key errors on the shared collection.
    existing = await db.users.find_one({"uid": uid}, {"_id": 0})
    fallback_name = (
        (fb_user.get("name") or fb_user.get("email") or "player").split("@")[0].strip()
        or "player"
    )
    if existing:
        # Existing Ace Chasers docs might lack `user_id` or `name`
        # (email/password Firebase signups have no displayName). Backfill
        # both so the league User model validates and league queries work.
        patch = {}
        if not existing.get("user_id"):
            patch["user_id"] = uid
            existing["user_id"] = uid
        if not existing.get("name"):
            name_val = existing.get("displayName") or fallback_name
            patch["name"] = name_val
            existing["name"] = name_val
        # Coerce email to a non-null string. Some pre-existing Ace Chasers
        # user docs have `email: None` (Firebase Google sign-in only kept
        # displayName). The Pydantic User model requires email: str, so a
        # None here would 500 every authenticated /api/leagues* call and
        # bounce the user back to /leagues/new with just a toast.
        if not existing.get("email"):
            email_val = fb_user.get("email") or ""
            patch["email"] = email_val
            existing["email"] = email_val
        if patch:
            await db.users.update_one({"uid": uid}, {"$set": patch})
        return existing
    doc = {
        "uid": uid,
        "user_id": uid,
        "email": fb_user.get("email") or "",
        "name": fallback_name,
        "picture": fb_user.get("picture") or fb_user.get("profilePictureUrl"),
        "handle": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.update_one({"uid": uid}, {"$setOnInsert": doc}, upsert=True)
    doc.pop("_id", None)
    return doc


async def get_current_user(
    request: Request = None,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> "User":
    """Bridged auth: verify Firebase Bearer token via the existing deps,
    then map the returned uid onto the league app's `User(user_id=...)`
    shape. Cookie/session args are kept for signature compatibility with
    the ported routes but are ignored."""
    fb = await _fb_get_current_user(authorization=authorization)
    if not fb or not fb.get("uid"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    uid = fb["uid"]
    doc = await _upsert_league_user(uid, fb)
    # `User` is defined lower in this file (MODELS section) — forward ref OK
    # at call time because the module is fully loaded before any request
    # handler runs.
    return User(**doc)


def now_iso():
    return datetime.now(timezone.utc).isoformat()




# ============= MODELS =============

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    handle: Optional[str] = None  # display name shown in leagues
    created_at: str = Field(default_factory=now_iso)

class League(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    location: str
    format: Literal["Singles", "Random-Draw Doubles", "BYOP", "Team", "Match Play"]
    description: Optional[str] = ""
    win_points: int = 10  # points for 1st place
    points_step: int = 2  # decrement per place
    ace_pool: float = 0.0
    entry_fee: float = 0.0  # per-round entry fee
    divisions: List[str] = Field(default_factory=lambda: ["Open"])
    payout_split: Dict[str, float] = Field(default_factory=lambda: {"pool": 0.7, "ace": 0.2, "club": 0.1})
    director_id: str  # user_id
    created_at: str = Field(default_factory=now_iso)

class LeagueCreate(BaseModel):
    name: str
    location: str
    format: Literal["Singles", "Random-Draw Doubles", "BYOP", "Team", "Match Play"]
    description: Optional[str] = ""
    win_points: int = 10
    points_step: int = 2
    entry_fee: float = 0.0
    divisions: Optional[List[str]] = None
    payout_split: Optional[Dict[str, float]] = None
    schedule: Optional[Dict[str, Any]] = None

class Season(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    name: str
    start_date: str
    end_date: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)

class Round(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    season_id: str
    name: str
    date: str  # ISO date
    holes: int = 18
    par_per_hole: List[int] = Field(default_factory=lambda: [3]*18)
    status: Literal["scheduled", "active", "completed"] = "scheduled"
    course_rating: Optional[float] = None
    director_notes: Optional[str] = ""
    ctp_holes: List[int] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)

class LeagueMember(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    user_id: str
    name: str  # cached
    picture: Optional[str] = None
    bag_tag: int  # rolling integer
    role: Literal["director", "player"] = "player"
    division: str = "Open"
    total_points: float = 0.0
    # Fair Play Terms agreement for the private Clubhouse feed. Persisted
    # per-league so the welcome overlay only renders once per member.
    clubhouse_agreed: bool = False
    clubhouse_agreed_at: Optional[str] = None
    joined_at: str = Field(default_factory=now_iso)

class Card(BaseModel):
    """A group of players playing together on one card"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_id: str
    label: str  # "Card A", "Card B"
    player_ids: List[str] = Field(default_factory=list)  # member_ids
    # When True, ANY teammate's score entry is applied to every player's
    # scorecard on this card (best-disc / scramble one-shared-score UX).
    # Consumed by `PATCH /api/cards/{id}/scramble-score`.
    scramble_mode: bool = False
    created_at: str = Field(default_factory=now_iso)

class ScoreEntry(BaseModel):
    hole: int
    strokes: int

class Scorecard(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_id: str
    league_id: str
    member_id: str
    card_id: Optional[str] = None
    scores: List[int] = Field(default_factory=lambda: [0]*18)  # strokes per hole (0 = unset)
    total: int = 0
    plus_minus: int = 0  # vs par
    handicap_at_round: float = 0.0
    version: int = 1
    # Certification / Proof-of-Score audit trail. Once finalized, the
    # score card is locked from further edits and the certifying user_id
    # is recorded here + into the proof_logs collection.
    finalized: bool = False
    certified: bool = False
    certified_by_user_id: Optional[str] = None
    certified_by_name: Optional[str] = None
    certified_at: Optional[str] = None
    updated_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)

class ProofLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scorecard_id: str
    round_id: str
    hole: int
    old_value: int
    new_value: int
    edited_by_user_id: str
    edited_by_name: str
    timestamp: str = Field(default_factory=now_iso)

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_id: str
    card_id: Optional[str] = None
    user_id: str
    user_name: str
    text: str
    timestamp: str = Field(default_factory=now_iso)

class LedgerEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    kind: Literal["debit", "credit"]
    category: Literal["Ace Pool", "CTP Cash", "Club Payout", "Entry Fee", "Weekly Payout", "Club Fund", "Other"]
    amount: float
    note: str = ""
    round_id: Optional[str] = None
    member_id: Optional[str] = None
    created_by: str
    created_at: str = Field(default_factory=now_iso)

class Announcement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    title: str
    body: str
    pinned: bool = True
    urgent: bool = False
    author_id: str
    author_name: str
    created_at: str = Field(default_factory=now_iso)

class LostFound(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    title: str
    description: str
    image_path: Optional[str] = None
    resolved: bool = False
    author_id: str
    author_name: str
    created_at: str = Field(default_factory=now_iso)

class StoryPost(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    image_path: str
    caption: Optional[str] = ""
    author_id: str
    author_name: str
    author_picture: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)

class FeedPost(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    league_id: str
    kind: Literal["post", "recap", "schedule"] = "post"
    title: Optional[str] = None
    body: str
    meta: Optional[Dict[str, Any]] = None  # for recap: hot_round, most_improved
    author_id: str
    author_name: str
    author_picture: Optional[str] = None
    # Optional media attached to a member post. Both are storage paths
    # returned by `/api/files/upload`. Set independently so a member can
    # post text + image, text + video, or media alone. Videos additionally
    # ship an optional `video_poster` frame captured client-side for
    # preview thumbnails.
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    video_poster: Optional[str] = None
    # `pinned` posts sort to the top of the feed. Used by the auto-schedule
    # publisher so newly-created rounds surface immediately in the clubhouse.
    pinned: bool = False
    created_at: str = Field(default_factory=now_iso)


# ============= AUTH (legacy Emergent OAuth stubs — retained for source-compat) =============
# The original cookie-session + OAuth endpoints have been superseded by the
# Firebase-backed `get_current_user` defined at the top of this file. Only
# `/api/auth/me` is kept (returns the current league user) — session_token
# and logout are handled by Firebase on the Ace Chasers side.


@api_router.get("/auth/me")
async def auth_me(request: Request,
                  session_token: Optional[str] = Cookie(None),
                  authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    return user.model_dump()


# ============= FILES =============
@api_router.post("/files/upload")
async def files_upload(
    request: Request,
    file: UploadFile = File(...),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Upload to Cloudinary (via the put_object compat shim) and return
    both the storage `path` (for source-compat with existing frontend code
    that stores it) AND the `url` — new frontend code should use the URL
    directly to skip a redirect."""
    user = await get_current_user(request, session_token, authorization)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    result = put_object(path, data, file.content_type or "application/octet-stream")
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "url": result["url"],
        "user_id": user.user_id,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "created_at": now_iso(),
    })
    return {"path": result["path"], "url": result["url"]}


@api_router.get("/files/{path:path}")
async def files_download(path: str, request: Request, auth: Optional[str] = Query(None),
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None)):
    """Look up the Cloudinary URL for a `storage_path` we handed out at
    upload time and 302 to it. Auth is checked via the Firebase bridge so
    only signed-in users can resolve paths."""
    # Prefer header, fall back to ?auth= query arg (used for <img> tags).
    if auth and not authorization:
        authorization = f"Bearer {auth}"
    await get_current_user(request, session_token, authorization)
    record = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    url = record.get("url")
    if not url:
        raise HTTPException(status_code=410, detail="File URL missing (legacy record)")
    return RedirectResponse(url=url, status_code=302)


# ============= LEAGUES =============
@api_router.post("/leagues")
async def create_league(payload: LeagueCreate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    league = League(
        name=payload.name, location=payload.location, format=payload.format,
        description=payload.description or "",
        win_points=payload.win_points, points_step=payload.points_step,
        entry_fee=float(payload.entry_fee or 0),
        divisions=payload.divisions or ["Open"],
        payout_split=payload.payout_split or {"pool": 0.7, "ace": 0.2, "club": 0.1},
        director_id=user.user_id,
    )
    await db.leagues.insert_one(league.model_dump())

    # Director joins as first member with bag_tag 1
    member = LeagueMember(league_id=league.id, user_id=user.user_id, name=user.name,
                          picture=user.picture, bag_tag=1, role="director")
    await db.league_members.insert_one(member.model_dump())

    # Create default season
    season = Season(league_id=league.id, name="Season 1", start_date=now_iso())
    await db.seasons.insert_one(season.model_dump())

    # Schedule generator
    schedule = payload.schedule or {}
    if schedule.get("weeks"):
        weeks = int(schedule.get("weeks", 8))
        start = schedule.get("start_date")
        rating = schedule.get("course_rating")
        try:
            base = datetime.fromisoformat(start) if start else datetime.now(timezone.utc)
        except Exception:
            base = datetime.now(timezone.utc)
        for i in range(weeks):
            rd = Round(
                league_id=league.id,
                season_id=season.id,
                name=f"Week {i+1}",
                date=(base + timedelta(days=7 * i)).isoformat(),
                course_rating=float(rating) if rating is not None else None,
            )
            await db.rounds.insert_one(rd.model_dump())

    return league.model_dump()


@api_router.get("/leagues")
async def list_leagues(request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    # Leagues user is a member of
    members = await db.league_members.find({"user_id": user.user_id}, {"_id": 0}).to_list(1000)
    league_ids = [m["league_id"] for m in members]
    leagues = await db.leagues.find({"id": {"$in": league_ids}}, {"_id": 0}).to_list(1000)
    # Attach member counts
    for lg in leagues:
        lg["member_count"] = await db.league_members.count_documents({"league_id": lg["id"]})
    return leagues


@api_router.get("/leagues/browse")
async def browse_leagues(request: Request,
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None)):
    await get_current_user(request, session_token, authorization)
    leagues = await db.leagues.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for lg in leagues:
        lg["member_count"] = await db.league_members.count_documents({"league_id": lg["id"]})
    return leagues


async def _require_member(league_id: str, user_id: str):
    m = await db.league_members.find_one({"league_id": league_id, "user_id": user_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=403, detail="Not a league member")
    return m


@api_router.get("/leagues/{league_id}")
async def get_league(league_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0})
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    membership = await db.league_members.find_one({"league_id": league_id, "user_id": user.user_id}, {"_id": 0})
    lg["is_member"] = bool(membership)
    lg["is_director"] = bool(membership and membership.get("role") == "director")
    lg["my_bag_tag"] = membership.get("bag_tag") if membership else None
    lg["my_clubhouse_agreed"] = bool(membership and membership.get("clubhouse_agreed"))
    lg["member_count"] = await db.league_members.count_documents({"league_id": league_id})
    return lg


@api_router.post("/leagues/{league_id}/join")
async def join_league(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0})
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    existing = await db.league_members.find_one({"league_id": league_id, "user_id": user.user_id}, {"_id": 0})
    if existing:
        return existing
    count = await db.league_members.count_documents({"league_id": league_id})
    member = LeagueMember(league_id=league_id, user_id=user.user_id, name=user.name,
                          picture=user.picture, bag_tag=count + 1)
    await db.league_members.insert_one(member.model_dump())
    return member.model_dump()


@api_router.get("/leagues/{league_id}/members")
async def list_members(league_id: str, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    members = await db.league_members.find({"league_id": league_id}, {"_id": 0}).sort("bag_tag", 1).to_list(500)
    return members


# ============= SEASONS =============
@api_router.get("/leagues/{league_id}/seasons")
async def list_seasons(league_id: str, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.seasons.find({"league_id": league_id}, {"_id": 0}).to_list(100)


# ============= ROUNDS =============
class RoundCreate(BaseModel):
    season_id: str
    name: str
    date: str
    holes: int = 18
    par_per_hole: Optional[List[int]] = None
    course_rating: Optional[float] = None
    # Optional free-text course/location string surfaced in the auto-published
    # scheduling announcement on the clubhouse feed. Doesn't affect scoring.
    course_location: Optional[str] = None
    # Turn off the auto-announcement when the caller only wants a private round.
    publish_announcement: bool = True

@api_router.post("/leagues/{league_id}/rounds")
async def create_round(league_id: str, payload: RoundCreate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director can create rounds")
    par = payload.par_per_hole or [3] * payload.holes
    rd = Round(league_id=league_id, season_id=payload.season_id, name=payload.name,
               date=payload.date, holes=payload.holes, par_per_hole=par,
               course_rating=payload.course_rating)
    await db.rounds.insert_one(rd.model_dump())

    # ── Auto-publish a pinned scheduling announcement to the clubhouse ──
    # Beautifully formatted, one-tap for the manager. The frontend renders
    # `pinned` posts at the top of the feed. Only fires when the caller
    # opted in (default true) and the round has a date.
    if payload.publish_announcement and payload.date:
        try:
            pretty_date = payload.date
            try:
                pretty_date = datetime.fromisoformat(payload.date.replace("Z", "")).strftime("%A, %b %d %Y")
            except Exception:
                pass
            body_lines = [
                f"📅  {pretty_date}",
                f"🥏  {payload.holes} holes · par {sum(par)}",
            ]
            if payload.course_location:
                body_lines.insert(1, f"📍  {payload.course_location.strip()}")
            body = "\n".join(body_lines)
            post = FeedPost(
                league_id=league_id, kind="schedule",
                title=f"Round scheduled — {payload.name}",
                body=body,
                meta={
                    "round_id": rd.id,
                    "round_date": payload.date,
                    "course_location": payload.course_location,
                },
                author_id=user.user_id, author_name=user.name,
                author_picture=user.picture,
                pinned=True,
            )
            await db.feed_posts.insert_one(post.model_dump())
        except Exception:
            logger.exception("Failed to auto-publish schedule for round %s", rd.id)
    return rd.model_dump()


@api_router.get("/leagues/{league_id}/rounds")
async def list_rounds(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.rounds.find({"league_id": league_id}, {"_id": 0}).sort("date", 1).to_list(500)


@api_router.get("/leagues/{league_id}/dashboard")
async def league_dashboard_bundle(league_id: str, request: Request,
                                   session_token: Optional[str] = Cookie(None),
                                   authorization: Optional[str] = Header(None)):
    """Single round-trip bundle for the league detail page. Returns the
    same shapes as the individual endpoints so the frontend can just
    destructure without re-mapping fields. Non-members still get the
    public league shape and empty lists — they need it to render the
    "Join League" CTA.
    """
    user = await get_current_user(request, session_token, authorization)
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0})
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    membership = await db.league_members.find_one(
        {"league_id": league_id, "user_id": user.user_id}, {"_id": 0}
    )
    is_member = bool(membership)
    is_director = bool(membership and membership.get("role") == "director")

    # Enrich league with the same is_member/is_director shape as GET
    # /leagues/{id} so the frontend can drop the field-mapping cost.
    lg["is_member"] = is_member
    lg["is_director"] = is_director
    lg["my_bag_tag"] = membership.get("bag_tag") if membership else None
    lg["my_clubhouse_agreed"] = bool(membership and membership.get("clubhouse_agreed"))

    # Members-only data (rounds, seasons, member list). Non-members get
    # empty lists so the client renders the join CTA cleanly.
    if is_member:
        seasons, rounds_list, members, member_count = await asyncio.gather(
            db.seasons.find({"league_id": league_id}, {"_id": 0}).to_list(100),
            db.rounds.find({"league_id": league_id}, {"_id": 0}).sort("date", 1).to_list(500),
            db.league_members.find({"league_id": league_id}, {"_id": 0}).sort("bag_tag", 1).to_list(500),
            db.league_members.count_documents({"league_id": league_id}),
        )
    else:
        seasons, rounds_list, members = [], [], []
        member_count = await db.league_members.count_documents({"league_id": league_id})

    lg["member_count"] = member_count
    return {
        "league": lg,
        "seasons": seasons,
        "rounds": rounds_list,
        "members": members,
    }



# ─── Moved to leagues_rounds_router.py (Phase 4): @api_router.get("/rounds/{round_id}")
# ─── Moved to leagues_rounds_router.py (Phase 4): class RoundStatusUpdate(BaseModel):
# ============= CARDS =============
# ─── Moved to leagues_rounds_router.py (Phase 4): class CardCreate(BaseModel):
# ============= SELF-SERVE ROUND JOIN =============
# ─── Moved to leagues_rounds_router.py (Phase 4): @api_router.post("/rounds/{round_id}/join")
# ============= SCORECARDS =============
# Moved to `leagues_rounds_router.py` (Phase 4 extraction, Feb 2026).
# The following endpoints now live in the rounds sub-router:
#   PATCH  /api/scorecards/{scorecard_id}/score
#   GET    /api/scorecards/{scorecard_id}/proof
#   POST   /api/scorecards/{scorecard_id}/finalize
#   POST   /api/scorecards/{scorecard_id}/certify
# They attach to the same shared `api_router` so URL surface is unchanged.


# ============= ROUND SWEEP FINALIZE (DIRECTOR) =============
# ─── Moved to leagues_rounds_router.py (Phase 4): class RoundSweepFinalizePayload(BaseModel):
@api_router.post("/leagues/{league_id}/clubhouse/agree")
async def agree_clubhouse_terms(league_id: str, request: Request,
                                 session_token: Optional[str] = Cookie(None),
                                 authorization: Optional[str] = Header(None)):
    """First-time Fair Play Terms agreement for the Clubhouse feed.
    Persists { clubhouse_agreed: True, clubhouse_agreed_at } on the
    LeagueMember doc so the welcome modal only renders once per member.
    """
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("clubhouse_agreed"):
        return {"ok": True, "already_agreed": True, "clubhouse_agreed_at": m.get("clubhouse_agreed_at")}
    now = now_iso()
    await db.league_members.update_one(
        {"id": m["id"]},
        {"$set": {"clubhouse_agreed": True, "clubhouse_agreed_at": now}},
    )
    return {"ok": True, "clubhouse_agreed": True, "clubhouse_agreed_at": now}


# ============= CHAT =============
# Moved to `leagues_rounds_router.py` (phase 3 of the router refactor).
# See tail-import block at the bottom of this file.


# ============= HANDICAP =============
async def _compute_handicap(league_id: str, member_id: str, par_per_hole: List[int]) -> float:
    """Average plus_minus of last 5 completed scorecards for member (in strokes)."""
    scs = await db.scorecards.find({"league_id": league_id, "member_id": member_id, "total": {"$gt": 0}},
                                   {"_id": 0}).sort("updated_at", -1).to_list(5)
    if not scs:
        return 0.0
    # Prefer course_rating-based differentials when available for PDGA-like accuracy
    diffs = []
    for s in scs:
        rd = await db.rounds.find_one({"id": s["round_id"]}, {"_id": 0}) or {}
        rating = rd.get("course_rating") or sum(rd.get("par_per_hole", par_per_hole))
        diffs.append(s.get("total", 0) - rating)
    return round(sum(diffs) / len(diffs), 2)


async def _compute_player_rating(league_id: str, member_id: str) -> float:
    """PDGA-style rating: 900 baseline + 10 points per stroke better than course rating (avg last 5)."""
    scs = await db.scorecards.find({"league_id": league_id, "member_id": member_id, "total": {"$gt": 0}},
                                   {"_id": 0}).sort("updated_at", -1).to_list(5)
    if not scs:
        return 0.0
    diffs = []
    for s in scs:
        rd = await db.rounds.find_one({"id": s["round_id"]}, {"_id": 0}) or {}
        rating = rd.get("course_rating") or sum(rd.get("par_per_hole", [3]*18))
        # +10 pts per stroke under rating, -10 per stroke over
        diffs.append((rating - s.get("total", 0)) * 10.0)
    return round(900.0 + (sum(diffs) / len(diffs)), 1)


@api_router.get("/leagues/{league_id}/handicaps")
async def get_handicaps(league_id: str, request: Request,
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    members = await db.league_members.find({"league_id": league_id}, {"_id": 0}).to_list(500)
    result = []
    for m in members:
        h = await _compute_handicap(league_id, m["id"], [3]*18)
        pr = await _compute_player_rating(league_id, m["id"])
        cnt = await db.scorecards.count_documents({"league_id": league_id, "member_id": m["id"], "total": {"$gt": 0}})
        result.append({"member_id": m["id"], "name": m["name"], "picture": m.get("picture"),
                       "handicap": h, "player_rating": pr, "rounds_played": cnt, "bag_tag": m["bag_tag"]})
    return result


# ============= FINALIZE ROUND =============
async def _finalize_round(round_id: str):
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        return
    league = await db.leagues.find_one({"id": rd["league_id"]}, {"_id": 0})
    if not league:
        return
    scs = await db.scorecards.find({"round_id": round_id, "total": {"$gt": 0}}, {"_id": 0}).to_list(500)
    if not scs:
        return
    # Compute net score = plus_minus - handicap
    for s in scs:
        s["net"] = s.get("plus_minus", 0) - s.get("handicap_at_round", 0)
    ranked = sorted(scs, key=lambda x: x["net"])  # lower is better

    win_pts = league.get("win_points", 10)
    step = league.get("points_step", 2)

    # Award points and swap bag tags
    hot_round = ranked[0]  # best net score
    prev_scores_by_member = {}
    for s in scs:
        prev = await db.scorecards.find({"league_id": rd["league_id"], "member_id": s["member_id"],
                                          "id": {"$ne": s["id"]}, "total": {"$gt": 0}}, {"_id": 0}
                                         ).sort("updated_at", -1).to_list(1)
        prev_scores_by_member[s["member_id"]] = prev[0].get("plus_minus") if prev else None

    for idx, s in enumerate(ranked):
        pts = max(win_pts - idx * step, 1)
        await db.league_members.update_one(
            {"id": s["member_id"]},
            {"$inc": {"total_points": pts}}
        )

    # Bag tag swap: winner claims lowest tag among participants; re-rank participants' tags by finish
    participant_ids = [s["member_id"] for s in ranked]
    members = await db.league_members.find({"id": {"$in": participant_ids}}, {"_id": 0}).to_list(500)
    tags = sorted([m["bag_tag"] for m in members])
    for idx, s in enumerate(ranked):
        await db.league_members.update_one({"id": s["member_id"]},
                                            {"$set": {"bag_tag": tags[idx]}})

    # Most Improved: biggest positive delta (previous plus_minus - current plus_minus)
    improvements = []
    for s in scs:
        prev = prev_scores_by_member.get(s["member_id"])
        if prev is None:
            continue
        delta = prev - s.get("plus_minus", 0)  # positive means improved
        improvements.append((s["member_id"], delta, s))
    most_improved = max(improvements, key=lambda t: t[1]) if improvements else None

    # Get member names
    def _member_name(mid):
        m = next((x for x in members if x["id"] == mid), None)
        return m["name"] if m else "Player"

    recap_meta = {
        "hot_round": {"member_id": hot_round["member_id"], "name": _member_name(hot_round["member_id"]),
                       "plus_minus": hot_round.get("plus_minus"), "total": hot_round.get("total")},
    }
    if most_improved:
        recap_meta["most_improved"] = {"member_id": most_improved[0], "name": _member_name(most_improved[0]),
                                        "delta": round(most_improved[1], 1)}

    post = FeedPost(league_id=rd["league_id"], kind="recap",
                    title=f"{rd['name']} Recap",
                    body=f"Round complete. Hot Round goes to {_member_name(hot_round['member_id'])}.",
                    meta=recap_meta,
                    author_id="system", author_name="Ace Chasers",
                    author_picture=None)
    await db.feed_posts.insert_one(post.model_dump())


# ============= LEADERBOARD / STANDINGS =============
@api_router.get("/leagues/{league_id}/standings")
async def standings(league_id: str, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    members = await db.league_members.find({"league_id": league_id}, {"_id": 0}).to_list(500)
    result = []
    for m in members:
        rounds_played = await db.scorecards.count_documents({"league_id": league_id, "member_id": m["id"], "total": {"$gt": 0}})
        result.append({
            "member_id": m["id"], "name": m["name"], "picture": m.get("picture"),
            "bag_tag": m["bag_tag"], "total_points": m.get("total_points", 0),
            "rounds_played": rounds_played,
        })
    result.sort(key=lambda x: (-x["total_points"], x["bag_tag"]))
    return result


# ============= LEDGER =============
# NOTE: Endpoints for `/leagues/{id}/ledger`, `/leagues/{id}/ledger.csv`,
# and `/leagues/{id}/entry-fees/collect` were extracted into
# `leagues_ledger_router.py` (phase 2 of the leagues_router refactor). It
# is imported at the BOTTOM of this file so its endpoints attach to the
# same `api_router` instance — same URL surface, same auth, no
# double-registration. Do not re-add them here; edit the extracted file.


# ============= FEED & CLUBHOUSE =============
# NOTE: Endpoints for announcements, lost-found, stories, and league feed
# were extracted into `leagues_clubhouse_router.py` (phase 1 of the
# leagues_router refactor). It is imported at the BOTTOM of this file
# (after ws_manager is defined) so we don't hit a circular import.


# ============= WEBSOCKETS =============
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict
import json as _json
import random as _random
import csv as _csv
from io import StringIO

class WSManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = defaultdict(list)
        self.lock = asyncio.Lock()

    async def connect(self, room: str, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.rooms[room].append(ws)

    async def disconnect(self, room: str, ws: WebSocket):
        async with self.lock:
            if ws in self.rooms.get(room, []):
                self.rooms[room].remove(ws)

    async def broadcast(self, room: str, message: dict):
        payload = _json.dumps(message, default=str)
        dead = []
        for ws in list(self.rooms.get(room, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self.lock:
                for ws in dead:
                    if ws in self.rooms.get(room, []):
                        self.rooms[room].remove(ws)

ws_manager = WSManager()

async def _validate_ws_token(token: str) -> Optional[dict]:
    """Verify a WebSocket bearer token.

    Historically this checked a `session_token` row in `db.user_sessions`,
    which was never populated by the current Firebase-backed auth path
    — so every socket handshake failed 4401 and the client looped
    "RECONNECTING…" forever. We now verify the Firebase JWT via the same
    `_fb_get_current_user` helper used by HTTP routes, then upsert/return
    the league user doc.
    """
    if not token:
        return None
    try:
        fb = await _fb_get_current_user(authorization=f"Bearer {token}")
    except Exception:
        return None
    if not fb or not fb.get("uid"):
        # Fallback for local dev tokens: preserve the legacy session_token
        # code path so any tooling that still uses it keeps working.
        session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if not session:
            return None
        return await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    doc = await _upsert_league_user(fb["uid"], fb)
    return doc

@api_router.websocket("/ws/rounds/{round_id}")
async def ws_round(websocket: WebSocket, round_id: str, token: str = Query(...)):
    user = await _validate_ws_token(token)
    if not user:
        await websocket.close(code=4401)
        return
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        await websocket.close(code=4404)
        return
    m = await db.league_members.find_one({"league_id": rd["league_id"], "user_id": user["user_id"]}, {"_id": 0})
    if not m:
        await websocket.close(code=4403)
        return
    room = f"round:{round_id}"
    await ws_manager.connect(room, websocket)
    try:
        # Initial hello
        await websocket.send_text(_json.dumps({"type": "hello", "user": user.get("name")}))
        while True:
            # Passive listener - client can send heartbeats. We ignore payload.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(room, websocket)

@api_router.websocket("/ws/leagues/{league_id}")
async def ws_league(websocket: WebSocket, league_id: str, token: str = Query(...)):
    user = await _validate_ws_token(token)
    if not user:
        await websocket.close(code=4401)
        return
    m = await db.league_members.find_one({"league_id": league_id, "user_id": user["user_id"]}, {"_id": 0})
    if not m:
        await websocket.close(code=4403)
        return
    room = f"league:{league_id}"
    await ws_manager.connect(room, websocket)
    try:
        await websocket.send_text(_json.dumps({"type": "hello"}))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(room, websocket)


# ============= AUTO-PAIR (Random-Draw Doubles) =============
class AutoPairPayload(BaseModel):
    member_ids: List[str]  # checked-in players
    card_size: int = 2  # 2 for doubles

# ─── Moved to leagues_rounds_router.py (Phase 4): @api_router.post("/rounds/{round_id}/auto-pair")
# ============= CSV EXPORTS =============
def _csv_response(rows: List[List[Any]], filename: str) -> Response:
    buf = StringIO()
    w = _csv.writer(buf)
    for r in rows:
        w.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# NOTE: `GET /api/leagues/{league_id}/standings.csv` moved to
# `leagues_rounds_router.py` (Phase 4 CSV consolidation). Client URL and
# response shape are unchanged.


# ============= PLAYER PROFILE =============
@api_router.get("/leagues/{league_id}/players/{member_id}")
async def player_profile(league_id: str, member_id: str, request: Request,
                           session_token: Optional[str] = Cookie(None),
                           authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    member = await db.league_members.find_one({"id": member_id, "league_id": league_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    scs = await db.scorecards.find({"league_id": league_id, "member_id": member_id, "total": {"$gt": 0}},
                                   {"_id": 0}).sort("updated_at", 1).to_list(500)
    history = []
    for s in scs:
        rd = await db.rounds.find_one({"id": s["round_id"]}, {"_id": 0}) or {}
        history.append({
            "round_id": s["round_id"],
            "round_name": rd.get("name"),
            "date": rd.get("date"),
            "total": s.get("total"),
            "plus_minus": s.get("plus_minus"),
            "course_rating": rd.get("course_rating") or sum(rd.get("par_per_hole", [3]*18)),
            "handicap_at_round": s.get("handicap_at_round", 0),
        })
    return {
        "member": member,
        "handicap": await _compute_handicap(league_id, member_id, [3]*18),
        "player_rating": await _compute_player_rating(league_id, member_id),
        "history": history,
    }


# ============= CTP MODEL =============
class CTPEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_id: str
    league_id: str
    hole: int
    member_id: str
    member_name: str
    feet: int
    inches: float  # 0..11.99
    created_at: str = Field(default_factory=now_iso)

    @property
    def total_inches(self) -> float:
        return self.feet * 12 + self.inches

def _to_inches(feet: int, inches: float) -> float:
    return float(feet) * 12.0 + float(inches)


# ============= ENTRY FEES (Escrow / 70-20-10 split) =============
# Extracted into `leagues_ledger_router.py`. See top-of-file LEDGER note.


# ============= DIVISION UPDATE =============
class DivisionPayload(BaseModel):
    division: str

@api_router.patch("/league-members/{member_id}/division")
async def set_division(member_id: str, payload: DivisionPayload, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await db.league_members.find_one({"id": member_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    caller = await _require_member(m["league_id"], user.user_id)
    # Directors can update anyone; players can update themselves
    if caller.get("role") != "director" and caller["id"] != member_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.league_members.update_one({"id": member_id}, {"$set": {"division": payload.division}})
    return {"ok": True, "division": payload.division}


# ============= DIRECTOR NOTES =============
class DirectorNotesPayload(BaseModel):
    director_notes: str
    ctp_holes: Optional[List[int]] = None
# Endpoint moved to `leagues_rounds_router.py`.


# ============= CTP ENTRIES =============
class CTPCreate(BaseModel):
    hole: int
    feet: int = 0
    inches: float = 0.0
    member_id: Optional[str] = None  # if omitted, use caller's membership
# Endpoints (POST/GET /rounds/{id}/ctp, DELETE /ctp/{entry_id}) moved to
# `leagues_rounds_router.py`.


# ============= PAYOUT DISTRIBUTION =============
# ─── Moved to leagues_rounds_router.py (Phase 4): @api_router.get("/rounds/{round_id}/payout")
# ─── Moved to leagues_rounds_router.py (Phase 4): @api_router.post("/rounds/{round_id}/finalize-payout")
# ============= PHASED REFACTOR: SUBMODULE REGISTRATION =============
# Import league submodules AFTER all shared symbols (api_router, db, models,
# ws_manager, helper functions) are defined so the submodules can safely
# `from .leagues_router import ...` without hitting a circular import.
# Each submodule attaches its endpoints to the same `api_router`, so the
# public URL surface is unchanged.
from . import leagues_clubhouse_router  # noqa: E402,F401
from . import leagues_ledger_router  # noqa: E402,F401
from . import leagues_compliance_router  # noqa: E402,F401
from . import leagues_rounds_router  # noqa: E402,F401
from . import leagues_extensions_router  # noqa: E402,F401
from . import leagues_advanced_router  # noqa: E402,F401
from . import leagues_bracket_router  # noqa: E402,F401
