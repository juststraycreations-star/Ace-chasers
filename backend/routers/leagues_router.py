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
    format: Literal["Singles", "Random-Draw Doubles", "BYOP", "Team"]
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
    format: Literal["Singles", "Random-Draw Doubles", "BYOP", "Team"]
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
    kind: Literal["post", "recap"] = "post"
    title: Optional[str] = None
    body: str
    meta: Optional[Dict[str, Any]] = None  # for recap: hot_round, most_improved
    author_id: str
    author_name: str
    author_picture: Optional[str] = None
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
    return rd.model_dump()


@api_router.get("/leagues/{league_id}/rounds")
async def list_rounds(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.rounds.find({"league_id": league_id}, {"_id": 0}).sort("date", 1).to_list(500)


@api_router.get("/rounds/{round_id}")
async def get_round(round_id: str, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    cards = await db.cards.find({"round_id": round_id}, {"_id": 0}).to_list(100)
    scorecards = await db.scorecards.find({"round_id": round_id}, {"_id": 0}).to_list(500)
    return {"round": rd, "cards": cards, "scorecards": scorecards}


class RoundStatusUpdate(BaseModel):
    status: Literal["scheduled", "active", "completed"]

@api_router.patch("/rounds/{round_id}/status")
async def update_round_status(round_id: str, payload: RoundStatusUpdate, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    await db.rounds.update_one({"id": round_id}, {"$set": {"status": payload.status}})
    if payload.status == "completed":
        await _finalize_round(round_id)
    return {"ok": True}


# ============= CARDS =============
class CardCreate(BaseModel):
    label: str
    player_ids: List[str]

@api_router.post("/rounds/{round_id}/cards")
async def create_card(round_id: str, payload: CardCreate, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    card = Card(round_id=round_id, label=payload.label, player_ids=payload.player_ids)
    await db.cards.insert_one(card.model_dump())
    # Create empty scorecards
    for pid in payload.player_ids:
        existing = await db.scorecards.find_one({"round_id": round_id, "member_id": pid})
        if existing:
            await db.scorecards.update_one({"round_id": round_id, "member_id": pid},
                                           {"$set": {"card_id": card.id}})
            continue
        handicap = await _compute_handicap(rd["league_id"], pid, rd["par_per_hole"])
        sc = Scorecard(round_id=round_id, league_id=rd["league_id"], member_id=pid,
                       card_id=card.id, scores=[0]*rd["holes"], handicap_at_round=handicap)
        await db.scorecards.insert_one(sc.model_dump())
    return card.model_dump()


# ============= SELF-SERVE ROUND JOIN =============
@api_router.post("/rounds/{round_id}/join")
async def join_round(round_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    """Self-serve endpoint that lets any league member sign themselves up
    for an existing round. Creates (or reuses) a solo card labeled with
    the member's name plus their scorecard. This is the counterpart to
    the director-only bulk create_card endpoint above.

    Idempotent — if the user already has a scorecard on the round, the
    existing card + scorecard are returned unchanged.
    """
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)

    # Idempotent short-circuit: already scored on this round.
    existing_sc = await db.scorecards.find_one(
        {"round_id": round_id, "member_id": m["id"]}, {"_id": 0}
    )
    if existing_sc and existing_sc.get("card_id"):
        existing_card = await db.cards.find_one({"id": existing_sc["card_id"]}, {"_id": 0})
        return {
            "already_joined": True,
            "card": existing_card,
            "scorecard": existing_sc,
        }

    # Create a solo card for this player.
    label = f"{m['name'].split(' ')[0]}'s Card"
    card = Card(round_id=round_id, label=label, player_ids=[m["id"]])
    await db.cards.insert_one(card.model_dump())

    # Create their scorecard (or link the existing one to the new card).
    if existing_sc:
        await db.scorecards.update_one(
            {"id": existing_sc["id"]},
            {"$set": {"card_id": card.id}},
        )
        sc = {**existing_sc, "card_id": card.id}
    else:
        handicap = await _compute_handicap(rd["league_id"], m["id"], rd["par_per_hole"])
        sc = Scorecard(
            round_id=round_id, league_id=rd["league_id"], member_id=m["id"],
            card_id=card.id, scores=[0]*rd["holes"], handicap_at_round=handicap,
        )
        await db.scorecards.insert_one(sc.model_dump())
        sc = sc.model_dump()

    await ws_manager.broadcast(
        f"round:{round_id}",
        {"type": "player_joined", "member_id": m["id"], "card_id": card.id},
    )
    return {
        "already_joined": False,
        "card": card.model_dump(),
        "scorecard": sc,
    }


# ============= SCORECARDS =============
class ScoreUpdate(BaseModel):
    hole: int  # 1-indexed
    strokes: int

@api_router.patch("/scorecards/{scorecard_id}/score")
async def update_score(scorecard_id: str, payload: ScoreUpdate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    sc = await db.scorecards.find_one({"id": scorecard_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    await _require_member(sc["league_id"], user.user_id)
    if payload.hole < 1 or payload.hole > len(sc["scores"]):
        raise HTTPException(status_code=400, detail="Invalid hole")

    idx = payload.hole - 1
    old_val = sc["scores"][idx]
    if sc.get("finalized"):
        raise HTTPException(status_code=409, detail="Scorecard already finalized")
    scores = list(sc["scores"])
    scores[idx] = int(payload.strokes)
    # totals
    total = sum(scores)
    rd = await db.rounds.find_one({"id": sc["round_id"]}, {"_id": 0})
    par_total = sum(rd["par_per_hole"][i] for i, s in enumerate(scores) if s > 0)
    played_strokes = sum(s for s in scores if s > 0)
    plus_minus = played_strokes - par_total if par_total > 0 else 0

    await db.scorecards.update_one(
        {"id": scorecard_id},
        {"$set": {"scores": scores, "total": total, "plus_minus": plus_minus,
                  "updated_at": now_iso()},
         "$inc": {"version": 1}}
    )
    log = ProofLog(scorecard_id=scorecard_id, round_id=sc["round_id"], hole=payload.hole,
                   old_value=old_val, new_value=int(payload.strokes),
                   edited_by_user_id=user.user_id, edited_by_name=user.name)
    await db.proof_logs.insert_one(log.model_dump())
    await ws_manager.broadcast(f"round:{sc['round_id']}", {
        "type": "score_update", "scorecard_id": scorecard_id, "hole": payload.hole,
        "strokes": int(payload.strokes), "total": total, "plus_minus": plus_minus,
        "edited_by": user.name,
    })
    return {"ok": True, "total": total, "plus_minus": plus_minus}


@api_router.get("/scorecards/{scorecard_id}/proof")
async def get_proof(scorecard_id: str, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    await get_current_user(request, session_token, authorization)
    logs = await db.proof_logs.find({"scorecard_id": scorecard_id}, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return logs


# ============= SCORECARD FINALIZE / CERTIFY =============
class ScorecardFinalizePayload(BaseModel):
    # The player or card captain MUST tick the certification checkbox in
    # the UI; the API rejects the payload otherwise. This value is
    # persisted onto the scorecard document as an authoritative record
    # that a human user reviewed and attested to the scores.
    certified: bool = False


@api_router.post("/scorecards/{scorecard_id}/finalize")
async def finalize_scorecard(scorecard_id: str, payload: ScorecardFinalizePayload,
                             request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    if not payload.certified:
        # Reject the payload if the certification checkbox was not ticked
        # in the UI. This is the enforcement point requested by the
        # legal compliance workflow.
        raise HTTPException(
            status_code=400,
            detail="Certification required. You must attest that the scores are accurate before finalizing.",
        )
    sc = await db.scorecards.find_one({"id": scorecard_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    await _require_member(sc["league_id"], user.user_id)
    if sc.get("finalized"):
        return {"ok": True, "already_finalized": True}
    now = now_iso()
    await db.scorecards.update_one(
        {"id": scorecard_id},
        {"$set": {
            "finalized": True,
            "certified": True,
            "certified_by_user_id": user.user_id,
            "certified_by_name": user.name,
            "certified_at": now,
            "updated_at": now,
        }},
    )
    # Log the certification into the Proof of Score audit trail so it
    # persists alongside every hole edit.
    audit = ProofLog(
        scorecard_id=scorecard_id,
        round_id=sc["round_id"],
        hole=0,
        old_value=0,
        new_value=int(sc.get("total") or 0),
        edited_by_user_id=user.user_id,
        edited_by_name=f"{user.name} · CERTIFIED",
    )
    await db.proof_logs.insert_one(audit.model_dump())
    await ws_manager.broadcast(
        f"round:{sc['round_id']}",
        {"type": "score_update", "scorecard_id": scorecard_id, "finalized": True},
    )
    return {
        "ok": True,
        "finalized": True,
        "certified_by_user_id": user.user_id,
        "certified_at": now,
    }


# ============= ROUND SWEEP FINALIZE (DIRECTOR) =============
class RoundSweepFinalizePayload(BaseModel):
    # Same certification pattern as the per-scorecard finalize. The
    # director MUST tick the certification checkbox in the sweep modal;
    # the API rejects the payload otherwise. Only unfinalized scorecards
    # for the round are updated; already-certified rows are skipped.
    certified: bool = False
    complete_round: bool = True  # also flip round.status -> completed


@api_router.post("/rounds/{round_id}/finalize")
async def finalize_round_sweep(round_id: str, payload: RoundSweepFinalizePayload,
                                request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    """Sweep-certify every scorecard on the round in one action. Director-only.
    Certification is required. Each affected scorecard gets a ProofLog audit
    entry stamped with the director's user_id and name, and optionally the
    round is marked completed (running the same standings recompute that the
    per-round /status endpoint uses).
    """
    user = await get_current_user(request, session_token, authorization)
    if not payload.certified:
        raise HTTPException(
            status_code=400,
            detail="Certification required. You must attest that the scores are accurate before finalizing.",
        )
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director can sweep-finalize a round")

    now = now_iso()
    open_scs = await db.scorecards.find(
        {"round_id": round_id, "finalized": {"$ne": True}}, {"_id": 0}
    ).to_list(500)
    certified_ids = []
    for sc in open_scs:
        await db.scorecards.update_one(
            {"id": sc["id"]},
            {"$set": {
                "finalized": True,
                "certified": True,
                "certified_by_user_id": user.user_id,
                "certified_by_name": f"{user.name} · DIRECTOR SWEEP",
                "certified_at": now,
                "updated_at": now,
            }},
        )
        audit = ProofLog(
            scorecard_id=sc["id"],
            round_id=round_id,
            hole=0,
            old_value=0,
            new_value=int(sc.get("total") or 0),
            edited_by_user_id=user.user_id,
            edited_by_name=f"{user.name} · DIRECTOR SWEEP-CERTIFIED",
        )
        await db.proof_logs.insert_one(audit.model_dump())
        certified_ids.append(sc["id"])

    round_status = rd.get("status")
    if payload.complete_round and round_status != "completed":
        await db.rounds.update_one({"id": round_id}, {"$set": {"status": "completed"}})
        await _finalize_round(round_id)
        round_status = "completed"

    await ws_manager.broadcast(
        f"round:{round_id}",
        {"type": "score_update", "sweep_finalized": True, "count": len(certified_ids)},
    )
    return {
        "ok": True,
        "certified_scorecard_ids": certified_ids,
        "already_finalized": (await db.scorecards.count_documents({"round_id": round_id})) - len(certified_ids),
        "round_status": round_status,
        "certified_by_user_id": user.user_id,
        "certified_at": now,
    }


# ============= CLUBHOUSE FAIR PLAY AGREEMENT =============
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
class ChatCreate(BaseModel):
    text: str
    card_id: Optional[str] = None

@api_router.post("/rounds/{round_id}/chat")
async def send_chat(round_id: str, payload: ChatCreate, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    msg = ChatMessage(round_id=round_id, card_id=payload.card_id, user_id=user.user_id,
                      user_name=user.name, text=payload.text)
    await db.chat_messages.insert_one(msg.model_dump())
    await ws_manager.broadcast(f"round:{round_id}", {"type": "chat", "message": msg.model_dump()})
    return msg.model_dump()


@api_router.get("/rounds/{round_id}/chat")
async def get_chat(round_id: str, request: Request,
                    card_id: Optional[str] = Query(None),
                    session_token: Optional[str] = Cookie(None),
                    authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    q = {"round_id": round_id}
    if card_id:
        q["card_id"] = card_id
    msgs = await db.chat_messages.find(q, {"_id": 0}).sort("timestamp", 1).to_list(500)
    return msgs


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
class LedgerCreate(BaseModel):
    kind: Literal["debit", "credit"]
    category: Literal["Ace Pool", "CTP Cash", "Club Payout", "Entry Fee", "Weekly Payout", "Club Fund", "Other"]
    amount: float
    note: Optional[str] = ""
    round_id: Optional[str] = None
    member_id: Optional[str] = None

@api_router.post("/leagues/{league_id}/ledger")
async def add_ledger(league_id: str, payload: LedgerCreate, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    entry = LedgerEntry(league_id=league_id, kind=payload.kind, category=payload.category,
                        amount=float(payload.amount), note=payload.note or "",
                        round_id=payload.round_id, member_id=payload.member_id, created_by=user.user_id)
    await db.ledger.insert_one(entry.model_dump())
    # Update ace pool total if applicable
    if payload.category == "Ace Pool":
        delta = payload.amount if payload.kind == "credit" else -payload.amount
        await db.leagues.update_one({"id": league_id}, {"$inc": {"ace_pool": delta}})
    return entry.model_dump()


@api_router.get("/leagues/{league_id}/ledger")
async def list_ledger(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    entries = await db.ledger.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    # aggregate by category
    totals = {}
    for e in entries:
        cat = e["category"]
        totals.setdefault(cat, {"credit": 0.0, "debit": 0.0})
        totals[cat][e["kind"]] += e["amount"]
    balance = sum(t["credit"] - t["debit"] for t in totals.values())
    return {"entries": entries, "totals": totals, "balance": balance}


# ============= FEED & CLUBHOUSE =============
# NOTE: Endpoints for announcements, lost-found, stories, and league feed
# were extracted into `leagues_clubhouse_router.py` (phase 1 of the
# leagues_router refactor). It is imported at the BOTTOM of this file
# (after ws_manager is defined) so we don't hit a circular import.


# ============= WEBSOCKETS =============
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict
import json as _json
import asyncio
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
    if not token:
        return None
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        return None
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    return user

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

@api_router.post("/rounds/{round_id}/auto-pair")
async def auto_pair(round_id: str, payload: AutoPairPayload, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")

    # Clear existing cards for this round
    await db.cards.delete_many({"round_id": round_id})
    await db.scorecards.delete_many({"round_id": round_id})

    ids = list(payload.member_ids)
    _random.shuffle(ids)
    size = max(1, int(payload.card_size))
    cards_created = []
    for i, chunk_start in enumerate(range(0, len(ids), size)):
        chunk = ids[chunk_start:chunk_start + size]
        label = chr(ord("A") + i)
        card = Card(round_id=round_id, label=f"Card {label}", player_ids=chunk)
        await db.cards.insert_one(card.model_dump())
        for pid in chunk:
            handicap = await _compute_handicap(rd["league_id"], pid, rd["par_per_hole"])
            sc = Scorecard(round_id=round_id, league_id=rd["league_id"], member_id=pid,
                           card_id=card.id, scores=[0]*rd["holes"], handicap_at_round=handicap)
            await db.scorecards.insert_one(sc.model_dump())
        cards_created.append(card.model_dump())

    await ws_manager.broadcast(f"round:{round_id}", {"type": "cards_updated"})
    return {"cards": cards_created}


# ============= CSV EXPORTS =============
def _csv_response(rows: List[List[Any]], filename: str) -> Response:
    buf = StringIO()
    w = _csv.writer(buf)
    for r in rows:
        w.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@api_router.get("/leagues/{league_id}/standings.csv")
async def standings_csv(league_id: str, request: Request,
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None),
                          auth: Optional[str] = Query(None)):
    hdr = authorization or (f"Bearer {auth}" if auth else None)
    user = await get_current_user(request, session_token, hdr)
    await _require_member(league_id, user.user_id)
    members = await db.league_members.find({"league_id": league_id}, {"_id": 0}).to_list(500)
    rows = [["Rank", "Player", "Points", "Rounds", "Handicap", "Player Rating", "Bag Tag"]]
    data = []
    for m in members:
        h = await _compute_handicap(league_id, m["id"], [3]*18)
        pr = await _compute_player_rating(league_id, m["id"])
        cnt = await db.scorecards.count_documents({"league_id": league_id, "member_id": m["id"], "total": {"$gt": 0}})
        data.append((m, h, pr, cnt))
    data.sort(key=lambda t: (-t[0].get("total_points", 0), t[0]["bag_tag"]))
    for i, (m, h, pr, cnt) in enumerate(data):
        rows.append([i + 1, m["name"], m.get("total_points", 0), cnt, h, pr, m["bag_tag"]])
    return _csv_response(rows, f"standings-{league_id}.csv")

@api_router.get("/leagues/{league_id}/ledger.csv")
async def ledger_csv(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None),
                       auth: Optional[str] = Query(None)):
    hdr = authorization or (f"Bearer {auth}" if auth else None)
    user = await get_current_user(request, session_token, hdr)
    await _require_member(league_id, user.user_id)
    entries = await db.ledger.find({"league_id": league_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    rows = [["Date", "Kind", "Category", "Amount", "Note"]]
    for e in entries:
        rows.append([e["created_at"], e["kind"], e["category"], e["amount"], e.get("note", "")])
    return _csv_response(rows, f"ledger-{league_id}.csv")


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
class EntryFeePayload(BaseModel):
    round_id: Optional[str] = None
    member_ids: List[str]  # players paying entry
    amount_override: Optional[float] = None  # per-player fee override

@api_router.post("/leagues/{league_id}/entry-fees/collect")
async def collect_entry_fees(league_id: str, payload: EntryFeePayload, request: Request,
                              session_token: Optional[str] = Cookie(None),
                              authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0})
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    per_player = float(payload.amount_override if payload.amount_override is not None else lg.get("entry_fee", 0))
    if per_player <= 0:
        raise HTTPException(status_code=400, detail="Entry fee is 0. Set league.entry_fee or pass amount_override.")

    split = lg.get("payout_split", {"pool": 0.7, "ace": 0.2, "club": 0.1})
    pool_pct = float(split.get("pool", 0.7))
    ace_pct = float(split.get("ace", 0.2))
    club_pct = float(split.get("club", 0.1))

    total = per_player * len(payload.member_ids)
    # 1) Record raw entry-fee credits per member
    for mid in payload.member_ids:
        mem = await db.league_members.find_one({"id": mid, "league_id": league_id}, {"_id": 0})
        note = f"Entry fee · {mem['name']}" if mem else "Entry fee"
        e = LedgerEntry(league_id=league_id, kind="credit", category="Entry Fee",
                         amount=per_player, note=note, round_id=payload.round_id, member_id=mid,
                         created_by=user.user_id)
        await db.ledger.insert_one(e.model_dump())

    # 2) Auto-split debits from escrow into 3 buckets (as credits to those categories)
    #    We use credit entries for each bucket so totals[category] tracks funds available.
    buckets = [
        ("Weekly Payout", total * pool_pct),
        ("Ace Pool", total * ace_pct),
        ("Club Fund", total * club_pct),
    ]
    for cat, amt in buckets:
        e = LedgerEntry(league_id=league_id, kind="credit", category=cat, amount=round(amt, 2),
                         note=f"Auto-split from {len(payload.member_ids)} × ${per_player:.2f} entries",
                         round_id=payload.round_id, created_by=user.user_id)
        await db.ledger.insert_one(e.model_dump())

    # And a matching debit of the total entry fees so net stays zero
    debit = LedgerEntry(league_id=league_id, kind="debit", category="Entry Fee",
                         amount=round(total, 2), note="Entry-fee escrow disbursement",
                         round_id=payload.round_id, created_by=user.user_id)
    await db.ledger.insert_one(debit.model_dump())

    # Update running ace_pool total
    await db.leagues.update_one({"id": league_id}, {"$inc": {"ace_pool": round(total * ace_pct, 2)}})

    return {
        "collected_from": len(payload.member_ids),
        "total": round(total, 2),
        "split": {"weekly_payout": round(total * pool_pct, 2),
                   "ace_pool": round(total * ace_pct, 2),
                   "club_fund": round(total * club_pct, 2)},
    }


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

@api_router.patch("/rounds/{round_id}/director-notes")
async def update_director_notes(round_id: str, payload: DirectorNotesPayload, request: Request,
                                  session_token: Optional[str] = Cookie(None),
                                  authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    update = {"director_notes": payload.director_notes}
    if payload.ctp_holes is not None:
        update["ctp_holes"] = payload.ctp_holes
    await db.rounds.update_one({"id": round_id}, {"$set": update})
    await ws_manager.broadcast(f"round:{round_id}", {
        "type": "director_notes", "director_notes": payload.director_notes,
        "ctp_holes": update.get("ctp_holes", rd.get("ctp_holes", [])),
    })
    return {"ok": True}


# ============= CTP ENTRIES =============
class CTPCreate(BaseModel):
    hole: int
    feet: int = 0
    inches: float = 0.0
    member_id: Optional[str] = None  # if omitted, use caller's membership

@api_router.post("/rounds/{round_id}/ctp")
async def create_ctp(round_id: str, payload: CTPCreate, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    caller = await _require_member(rd["league_id"], user.user_id)
    member_id = payload.member_id or caller["id"]
    mem = await db.league_members.find_one({"id": member_id, "league_id": rd["league_id"]}, {"_id": 0})
    if not mem:
        raise HTTPException(status_code=404, detail="Member not found")
    if payload.hole < 1 or payload.hole > rd.get("holes", 18):
        raise HTTPException(status_code=400, detail="Invalid hole")
    if payload.feet < 0 or payload.inches < 0 or payload.inches >= 12:
        raise HTTPException(status_code=400, detail="Invalid distance (inches must be 0..11.99)")
    entry = CTPEntry(round_id=round_id, league_id=rd["league_id"], hole=payload.hole,
                      member_id=member_id, member_name=mem["name"],
                      feet=int(payload.feet), inches=float(payload.inches))
    await db.ctp_entries.insert_one(entry.model_dump())
    await ws_manager.broadcast(f"round:{round_id}", {"type": "ctp_entry", "entry": entry.model_dump()})
    return entry.model_dump()


@api_router.get("/rounds/{round_id}/ctp")
async def list_ctp(round_id: str, request: Request,
                    session_token: Optional[str] = Cookie(None),
                    authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    entries = await db.ctp_entries.find({"round_id": round_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    # Build leaderboard grouped by hole (best = smallest distance)
    by_hole: Dict[int, List[dict]] = {}
    for e in entries:
        e["distance_inches"] = e["feet"] * 12 + e["inches"]
        by_hole.setdefault(e["hole"], []).append(e)
    leaderboard = {}
    for hole, items in by_hole.items():
        items.sort(key=lambda x: x["distance_inches"])
        leaderboard[hole] = items
    return {"entries": entries, "leaderboard": leaderboard, "ctp_holes": rd.get("ctp_holes", [])}


@api_router.delete("/ctp/{entry_id}")
async def delete_ctp(entry_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    e = await db.ctp_entries.find_one({"id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    caller = await _require_member(e["league_id"], user.user_id)
    # Own entries or director
    if caller.get("role") != "director" and caller["id"] != e["member_id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.ctp_entries.delete_one({"id": entry_id})
    await ws_manager.broadcast(f"round:{e['round_id']}", {"type": "ctp_deleted", "entry_id": entry_id})
    return {"ok": True}


# ============= PAYOUT DISTRIBUTION =============
@api_router.get("/rounds/{round_id}/payout")
async def get_payout(round_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    lg = await db.leagues.find_one({"id": rd["league_id"]}, {"_id": 0})

    # Weekly Payout pool available for this round: entries with round_id=round_id and category=Weekly Payout
    pool_credits = await db.ledger.find({"league_id": rd["league_id"], "round_id": round_id,
                                          "category": "Weekly Payout", "kind": "credit"}, {"_id": 0}).to_list(500)
    pool_debits = await db.ledger.find({"league_id": rd["league_id"], "round_id": round_id,
                                          "category": "Weekly Payout", "kind": "debit"}, {"_id": 0}).to_list(500)
    pool_available = sum(e["amount"] for e in pool_credits) - sum(e["amount"] for e in pool_debits)

    # Scorecards + members
    scs = await db.scorecards.find({"round_id": round_id, "total": {"$gt": 0}}, {"_id": 0}).to_list(500)
    members = await db.league_members.find({"league_id": rd["league_id"]}, {"_id": 0}).to_list(500)
    mmap = {m["id"]: m for m in members}

    # Group by division
    divisions_out = {}
    for s in scs:
        mem = mmap.get(s["member_id"])
        if not mem:
            continue
        div = mem.get("division", "Open")
        divisions_out.setdefault(div, []).append({
            "member_id": s["member_id"],
            "name": mem["name"],
            "picture": mem.get("picture"),
            "total": s["total"],
            "plus_minus": s.get("plus_minus", 0),
            "handicap_at_round": s.get("handicap_at_round", 0),
            "net": s.get("total", 0) - s.get("handicap_at_round", 0),
        })

    # Distribute pool across divisions proportional to # players, then payout curve within each division
    # Curve: 50/30/20 top-3 payouts; if fewer players, only top gets everything.
    payouts = {}
    total_players = sum(len(v) for v in divisions_out.values()) or 1
    for div, players in divisions_out.items():
        players.sort(key=lambda p: (p["net"], p["total"]))
        div_pool = round(pool_available * (len(players) / total_players), 2)
        curve = [0.5, 0.3, 0.2][: min(3, len(players))]
        remaining = 1 - sum(curve)
        if remaining > 0 and curve:
            curve[0] += remaining
        div_payouts = []
        for i, p in enumerate(players):
            share = curve[i] if i < len(curve) else 0
            amount = round(div_pool * share, 2)
            div_payouts.append({
                **p,
                "place": i + 1,
                "payout": amount,
            })
        payouts[div] = {
            "players": div_payouts,
            "pool": div_pool,
        }

    return {
        "round_id": round_id,
        "round_name": rd.get("name"),
        "pool_available": round(pool_available, 2),
        "divisions": payouts,
        "payout_split": lg.get("payout_split", {"pool": 0.7, "ace": 0.2, "club": 0.1}),
    }


# ============= WEEKLY PAYOUT FINALIZE =============
@api_router.post("/rounds/{round_id}/finalize-payout")
async def finalize_payout(round_id: str, request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    """Convert the payout distribution into ledger debit entries against the Weekly Payout pool."""
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    dist = await get_payout(round_id, request, session_token, authorization)
    entries = []
    for div, block in dist["divisions"].items():
        for p in block["players"]:
            if p["payout"] > 0:
                e = LedgerEntry(league_id=rd["league_id"], kind="debit", category="Weekly Payout",
                                 amount=float(p["payout"]),
                                 note=f"Payout · {p['name']} ({div} · P{p['place']})",
                                 round_id=round_id, member_id=p["member_id"],
                                 created_by=user.user_id)
                await db.ledger.insert_one(e.model_dump())
                entries.append(e.model_dump())
    return {"created": len(entries), "entries": entries}


# The router is included by the main Ace Chasers server.py with the /api
# prefix. CORS is handled globally by the main app. No shutdown handler
# is needed here — the main app owns the Mongo client lifecycle.

# ============= PHASED REFACTOR: SUBMODULE REGISTRATION =============
# Import league submodules AFTER all shared symbols (api_router, db, models,
# ws_manager, helper functions) are defined so the submodules can safely
# `from .leagues_router import ...` without hitting a circular import.
# Each submodule attaches its endpoints to the same `api_router`, so the
# public URL surface is unchanged.
from . import leagues_clubhouse_router  # noqa: E402,F401
