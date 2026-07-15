from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Header, Query, Response, Cookie, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Dict, Any
import uuid
import requests
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

APP_NAME = os.environ.get('APP_NAME', 'acechasers')
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY')
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
AUTH_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

app = FastAPI()
api_router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ============= STORAGE =============
storage_key: Optional[str] = None

def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


# ============= MODELS =============
def now_iso():
    return datetime.now(timezone.utc).isoformat()

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
    director_id: str  # user_id
    created_at: str = Field(default_factory=now_iso)

class LeagueCreate(BaseModel):
    name: str
    location: str
    format: Literal["Singles", "Random-Draw Doubles", "BYOP", "Team"]
    description: Optional[str] = ""
    win_points: int = 10
    points_step: int = 2
    schedule: Optional[Dict[str, Any]] = None  # {weekday, start_date, weeks, time}

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
    total_points: float = 0.0
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
    category: Literal["Ace Pool", "CTP Cash", "Club Payout", "Entry Fee", "Other"]
    amount: float
    note: str = ""
    round_id: Optional[str] = None
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


# ============= AUTH =============
async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> User:
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**user_doc)


class SessionExchange(BaseModel):
    session_id: str

@api_router.post("/auth/session")
async def auth_session(payload: SessionExchange, response: Response):
    """Exchange session_id from OAuth redirect for a persistent session_token."""
    resp = requests.get(
        AUTH_SESSION_URL,
        headers={"X-Session-ID": payload.session_id},
        timeout=15,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = resp.json()

    # Upsert user
    existing = await db.users.find_one({"email": data["email"]}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name", existing["name"]), "picture": data.get("picture")}}
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": data["email"],
            "name": data.get("name", ""),
            "picture": data.get("picture"),
            "handle": data.get("name", "").split(" ")[0] if data.get("name") else "",
            "created_at": now_iso(),
        })

    session_token = data["session_token"]
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires.isoformat(),
        "created_at": now_iso(),
    })

    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user_doc, "session_token": session_token}


@api_router.get("/auth/me")
async def auth_me(request: Request,
                  session_token: Optional[str] = Cookie(None),
                  authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    return user.model_dump()


@api_router.post("/auth/logout")
async def logout(response: Response,
                 session_token: Optional[str] = Cookie(None),
                 authorization: Optional[str] = Header(None)):
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"ok": True}


# ============= FILES =============
@api_router.post("/files/upload")
async def files_upload(
    request: Request,
    file: UploadFile = File(...),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(request, session_token, authorization)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    result = put_object(path, data, file.content_type or "application/octet-stream")
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "user_id": user.user_id,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "created_at": now_iso(),
    })
    return {"path": result["path"]}


@api_router.get("/files/{path:path}")
async def files_download(path: str, auth: Optional[str] = Query(None),
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None)):
    # Any authenticated user can download. Validate session via any of the auth mechanisms.
    token = session_token or auth
    header_auth = authorization
    if not token and not header_auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if auth and not session_token and not authorization:
        header_auth = f"Bearer {auth}"
    session_doc = None
    check_token = token or (header_auth.split(" ", 1)[1] if header_auth and header_auth.startswith("Bearer ") else None)
    if check_token:
        session_doc = await db.user_sessions.find_one({"session_token": check_token}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid session")

    record = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, ct = get_object(path)
    return Response(content=data, media_type=record.get("content_type") or ct)


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
    category: Literal["Ace Pool", "CTP Cash", "Club Payout", "Entry Fee", "Other"]
    amount: float
    note: Optional[str] = ""
    round_id: Optional[str] = None

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
                        round_id=payload.round_id, created_by=user.user_id)
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
class AnnouncementCreate(BaseModel):
    title: str
    body: str
    urgent: bool = False

@api_router.post("/leagues/{league_id}/announcements")
async def create_announcement(league_id: str, payload: AnnouncementCreate, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    a = Announcement(league_id=league_id, title=payload.title, body=payload.body,
                     urgent=payload.urgent, author_id=user.user_id, author_name=user.name)
    await db.announcements.insert_one(a.model_dump())
    await ws_manager.broadcast(f"league:{league_id}", {"type": "announcement", "announcement": a.model_dump()})
    return a.model_dump()


@api_router.get("/leagues/{league_id}/announcements")
async def list_announcements(league_id: str, request: Request,
                              session_token: Optional[str] = Cookie(None),
                              authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.announcements.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api_router.delete("/announcements/{announcement_id}")
async def delete_announcement(announcement_id: str, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    a = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    m = await _require_member(a["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    await db.announcements.delete_one({"id": announcement_id})
    return {"ok": True}


class LostFoundCreate(BaseModel):
    title: str
    description: str
    image_path: Optional[str] = None

@api_router.post("/leagues/{league_id}/lost-found")
async def create_lost_found(league_id: str, payload: LostFoundCreate, request: Request,
                              session_token: Optional[str] = Cookie(None),
                              authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    lf = LostFound(league_id=league_id, title=payload.title, description=payload.description,
                    image_path=payload.image_path, author_id=user.user_id, author_name=user.name)
    await db.lost_found.insert_one(lf.model_dump())
    return lf.model_dump()


@api_router.get("/leagues/{league_id}/lost-found")
async def list_lost_found(league_id: str, request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.lost_found.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api_router.patch("/lost-found/{item_id}/resolve")
async def resolve_lost_found(item_id: str, request: Request,
                               session_token: Optional[str] = Cookie(None),
                               authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    item = await db.lost_found.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    await _require_member(item["league_id"], user.user_id)
    await db.lost_found.update_one({"id": item_id}, {"$set": {"resolved": True}})
    return {"ok": True}


class StoryCreate(BaseModel):
    image_path: str
    caption: Optional[str] = ""

@api_router.post("/leagues/{league_id}/stories")
async def create_story(league_id: str, payload: StoryCreate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    s = StoryPost(league_id=league_id, image_path=payload.image_path, caption=payload.caption or "",
                   author_id=user.user_id, author_name=user.name, author_picture=user.picture)
    await db.stories.insert_one(s.model_dump())
    return s.model_dump()


@api_router.get("/leagues/{league_id}/stories")
async def list_stories(league_id: str, request: Request,
                         session_token: Optional[str] = Cookie(None),
                         authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    # Show stories from the last 48 hours
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    return await db.stories.find({"league_id": league_id, "created_at": {"$gte": cutoff}},
                                   {"_id": 0}).sort("created_at", -1).to_list(100)


class FeedPostCreate(BaseModel):
    body: str
    title: Optional[str] = None

@api_router.post("/leagues/{league_id}/feed")
async def create_feed_post(league_id: str, payload: FeedPostCreate, request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    p = FeedPost(league_id=league_id, kind="post", title=payload.title, body=payload.body,
                  author_id=user.user_id, author_name=user.name, author_picture=user.picture)
    await db.feed_posts.insert_one(p.model_dump())
    return p.model_dump()


@api_router.get("/leagues/{league_id}/feed")
async def list_feed(league_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.feed_posts.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(200)


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

@app.websocket("/api/ws/rounds/{round_id}")
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

@app.websocket("/api/ws/leagues/{league_id}")
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


# ============= INCLUDE =============
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
