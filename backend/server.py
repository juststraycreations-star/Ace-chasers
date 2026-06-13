"""Ace Chasers backend API.

All app routes are prefixed with /api and protected by `get_current_user`
(Firebase ID token via Authorization: Bearer). Endpoints:

  POST /api/auth/sync       Upsert the user record for the caller, then ensure
                            inbound demo likes exist (for matched-likes demo).
  GET  /api/users/me        Return the caller's profile.
  PUT  /api/users/me        Update the caller's profile.
  GET  /api/discovery       List candidate players to swipe on (excludes the
                            caller and anyone already swiped).
  POST /api/swipes          Body: {target_uid, action: like|pass}. Records the
                            swipe and, on a mutual like, creates a Match.
  GET  /api/likes           List profiles the caller has liked + match state.
  POST /api/matches/{uid}/friend   Mark a match as friended.
  DELETE /api/likes/{uid}   Remove a like (and any related match).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Literal, Optional

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from db import (  # noqa: E402  (load_dotenv must run first)
    ensure_indexes,
    ensure_inbound_likes_for,
    get_db,
    seed_demo_users,
)
from firebase_auth import get_current_user, init_firebase  # noqa: E402
from invites import (  # noqa: E402
    create_invite,
    list_invites,
    redeem_invite,
    revoke_invite,
)

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Ace Chasers API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models -----------------------------------------------------------------

class ProfileIn(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    skillLevel: Optional[str] = None
    location: Optional[str] = None
    favoriteCourse: Optional[str] = None
    favoriteFrisbee: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[List[str]] = None
    profilePictureUrl: Optional[str] = None


class AuthSyncIn(BaseModel):
    invite_code: Optional[str] = None


class InviteCreateIn(BaseModel):
    email: Optional[str] = None
    expires_at: Optional[str] = None


class ProfileOut(BaseModel):
    uid: str
    email: Optional[str] = None
    emailVerified: bool = False
    name: Optional[str] = None
    age: Optional[int] = None
    skillLevel: Optional[str] = None
    location: Optional[str] = None
    favoriteCourse: Optional[str] = None
    favoriteFrisbee: Optional[str] = None
    bio: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    profilePictureUrl: Optional[str] = None


class SwipeIn(BaseModel):
    target_uid: str
    action: Literal["like", "pass"]


class LikeOut(BaseModel):
    player: ProfileOut
    likedAt: str
    matched: bool
    friended: bool


# --- Helpers ----------------------------------------------------------------

def _user_to_profile(doc: dict, *, email_verified: Optional[bool] = None) -> ProfileOut:
    return ProfileOut(
        uid=doc["uid"],
        email=doc.get("email"),
        emailVerified=bool(email_verified if email_verified is not None else doc.get("email_verified", False)),
        name=doc.get("name"),
        age=doc.get("age"),
        skillLevel=doc.get("skillLevel"),
        location=doc.get("location"),
        favoriteCourse=doc.get("favoriteCourse"),
        favoriteFrisbee=doc.get("favoriteFrisbee"),
        bio=doc.get("bio"),
        interests=doc.get("interests") or [],
        profilePictureUrl=doc.get("profilePictureUrl"),
    )


def _match_key(a: str, b: str) -> tuple[str, str]:
    """Canonical (low, high) ordering so the unique index works regardless of
    who liked first."""
    return (a, b) if a < b else (b, a)


def _require_invite_enabled() -> bool:
    return os.environ.get("REQUIRE_INVITE", "false").strip().lower() in {"1", "true", "yes"}


def _claims_email_verified(claims: dict) -> bool:
    # Firebase Admin returns `email_verified`. Our dev path may set the same.
    if "email_verified" in claims:
        return bool(claims["email_verified"])
    # Dev fallback: no info → treat as verified so devs aren't blocked by
    # the banner. Real deployments always have the field.
    return True


async def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> bool:
    expected = os.environ.get("ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return True


# --- Lifecycle --------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    init_firebase()
    await ensure_indexes()
    await seed_demo_users()


# --- Routes -----------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    """Public config consumed by the frontend on app load."""
    return {"require_invite": _require_invite_enabled()}


@app.post("/api/auth/sync", response_model=ProfileOut)
async def auth_sync(
    payload: AuthSyncIn = Body(default_factory=AuthSyncIn),
    current=Depends(get_current_user),
):
    """Idempotently upsert the user record for the caller. New users may need
    to redeem an invite code when REQUIRE_INVITE is enabled. Existing users
    always pass through (no retroactive gating)."""
    db = get_db()
    existing = await db.users.find_one({"uid": current["uid"]})
    is_new_user = existing is None

    if is_new_user and _require_invite_enabled():
        await redeem_invite(
            code=(payload.invite_code or "").strip(),
            uid=current["uid"],
            email=current.get("email"),
        )

    now = datetime.now(timezone.utc).isoformat()
    email_verified = _claims_email_verified(current.get("claims") or {})
    update = {
        "$setOnInsert": {
            "uid": current["uid"],
            "created_at": now,
            "is_seed": False,
            "interests": ["casual play"],
            "skillLevel": "Beginner",
            "bio": "New to Ace Chasers!",
        },
        "$set": {
            "email": current.get("email"),
            "email_verified": email_verified,
            "updated_at": now,
        },
    }
    if current.get("name"):
        update["$setOnInsert"]["name"] = current["name"]
    if current.get("picture"):
        update["$setOnInsert"]["profilePictureUrl"] = current["picture"]

    await db.users.update_one({"uid": current["uid"]}, update, upsert=True)
    await ensure_inbound_likes_for(current["uid"])

    doc = await db.users.find_one({"uid": current["uid"]})
    return _user_to_profile(doc, email_verified=email_verified)


@app.get("/api/users/me", response_model=ProfileOut)
async def get_me(current=Depends(get_current_user)):
    db = get_db()
    doc = await db.users.find_one({"uid": current["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found — call /api/auth/sync first")
    email_verified = _claims_email_verified(current.get("claims") or {})
    return _user_to_profile(doc, email_verified=email_verified)


# --- Admin: invitations -----------------------------------------------------

@app.get("/api/admin/invites")
async def admin_list_invites(_: bool = Depends(require_admin)):
    return await list_invites()


@app.post("/api/admin/invites")
async def admin_create_invite(payload: InviteCreateIn, _: bool = Depends(require_admin)):
    return await create_invite(email=payload.email, expires_at=payload.expires_at)


@app.delete("/api/admin/invites/{code}")
async def admin_revoke_invite(code: str, _: bool = Depends(require_admin)):
    ok = await revoke_invite(code)
    if not ok:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"ok": True}


@app.put("/api/users/me", response_model=ProfileOut)
async def update_me(payload: ProfileIn, current=Depends(get_current_user)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"uid": current["uid"]}, {"$set": updates}, upsert=True)
    doc = await db.users.find_one({"uid": current["uid"]})
    return _user_to_profile(doc, email_verified=_claims_email_verified(current.get("claims") or {}))


@app.get("/api/discovery", response_model=List[ProfileOut])
async def discovery(current=Depends(get_current_user)):
    db = get_db()
    # Players already swiped on by the caller
    swiped_cursor = db.swipes.find({"from_uid": current["uid"]}, {"to_uid": 1})
    swiped_uids = [d["to_uid"] async for d in swiped_cursor]
    exclude = set(swiped_uids + [current["uid"]])

    cursor = db.users.find({"uid": {"$nin": list(exclude)}}).limit(50)
    out: list[ProfileOut] = []
    async for doc in cursor:
        out.append(_user_to_profile(doc))
    return out


@app.post("/api/swipes")
async def post_swipe(payload: SwipeIn, current=Depends(get_current_user)):
    db = get_db()
    if payload.target_uid == current["uid"]:
        raise HTTPException(status_code=400, detail="Cannot swipe on yourself")

    target = await db.users.find_one({"uid": payload.target_uid})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.swipes.update_one(
        {"from_uid": current["uid"], "to_uid": payload.target_uid},
        {
            "$set": {
                "from_uid": current["uid"],
                "to_uid": payload.target_uid,
                "action": payload.action,
                "created_at": now,
            }
        },
        upsert=True,
    )

    matched = False
    if payload.action == "like":
        # Did the target previously like the caller? -> match
        reverse = await db.swipes.find_one(
            {"from_uid": payload.target_uid, "to_uid": current["uid"], "action": "like"}
        )
        if reverse:
            a, b = _match_key(current["uid"], payload.target_uid)
            await db.matches.update_one(
                {"user_a": a, "user_b": b},
                {
                    "$setOnInsert": {
                        "user_a": a,
                        "user_b": b,
                        "friended_by": [],
                        "created_at": now,
                    }
                },
                upsert=True,
            )
            matched = True

    return {"ok": True, "matched": matched}


@app.get("/api/likes", response_model=List[LikeOut])
async def list_likes(current=Depends(get_current_user)):
    db = get_db()
    cursor = db.swipes.find({"from_uid": current["uid"], "action": "like"}).sort("created_at", -1)
    out: list[LikeOut] = []
    async for swipe in cursor:
        target = await db.users.find_one({"uid": swipe["to_uid"]})
        if not target:
            continue
        a, b = _match_key(current["uid"], swipe["to_uid"])
        match_doc = await db.matches.find_one({"user_a": a, "user_b": b})
        friended = bool(match_doc and current["uid"] in (match_doc.get("friended_by") or []))
        out.append(
            LikeOut(
                player=_user_to_profile(target),
                likedAt=swipe.get("created_at", ""),
                matched=match_doc is not None,
                friended=friended,
            )
        )
    return out


@app.post("/api/matches/{target_uid}/friend")
async def add_friend(target_uid: str, current=Depends(get_current_user)):
    db = get_db()
    a, b = _match_key(current["uid"], target_uid)
    match = await db.matches.find_one({"user_a": a, "user_b": b})
    if not match:
        raise HTTPException(status_code=404, detail="No match exists with this user yet")
    await db.matches.update_one(
        {"user_a": a, "user_b": b},
        {"$addToSet": {"friended_by": current["uid"]}},
    )
    return {"ok": True}


@app.delete("/api/likes/{target_uid}")
async def remove_like(target_uid: str, current=Depends(get_current_user)):
    db = get_db()
    await db.swipes.delete_one(
        {"from_uid": current["uid"], "to_uid": target_uid, "action": "like"}
    )
    a, b = _match_key(current["uid"], target_uid)
    await db.matches.delete_one({"user_a": a, "user_b": b})
    return {"ok": True}
