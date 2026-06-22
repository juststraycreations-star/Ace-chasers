"""Auth + profile routes: /api/auth/sync, /api/users/me, /api/users/{uid}."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db
from deps import (
    claims_email_verified,
    require_invite_enabled,
    strip_private_fields,
    user_to_profile,
)
from firebase_auth import get_current_user
from geocode import geocode_location
from invites import redeem_invite
from models import AuthSyncIn, ProfileIn, ProfileOut


router = APIRouter()


@router.post("/api/auth/sync", response_model=ProfileOut)
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

    if is_new_user and require_invite_enabled():
        await redeem_invite(
            code=(payload.invite_code or "").strip(),
            uid=current["uid"],
            email=current.get("email"),
        )

    now = datetime.now(timezone.utc).isoformat()
    email_verified = claims_email_verified(current.get("claims") or {})
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
    # Seed users + auto-likes are disabled in production — real users only.

    doc = await db.users.find_one({"uid": current["uid"]})
    return user_to_profile(doc, email_verified=email_verified)


@router.get("/api/users/me", response_model=ProfileOut)
async def get_me(current=Depends(get_current_user)):
    db = get_db()
    doc = await db.users.find_one({"uid": current["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found — call /api/auth/sync first")
    email_verified = claims_email_verified(current.get("claims") or {})
    return user_to_profile(doc, email_verified=email_verified)


@router.put("/api/users/me", response_model=ProfileOut)
async def update_me(payload: ProfileIn, current=Depends(get_current_user)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    # Geocode whenever the location field is explicitly included in the
    # payload. Empty string clears the coords; resolvable text stores them.
    if "location" in updates:
        loc = (updates.get("location") or "").strip()
        if not loc:
            updates["lat"] = None
            updates["lng"] = None
        else:
            coords = await geocode_location(loc)
            if coords is not None:
                updates["lat"], updates["lng"] = coords
            else:
                # Unresolvable text -> drop stale coords so distance filter
                # doesn't return a wrong result.
                updates["lat"] = None
                updates["lng"] = None
    # Ace Club: clearing the bool always clears the count too, so a player
    # who toggles off can't leave a stale ace count behind.
    if updates.get("aceClub") is False:
        updates["aceClubCount"] = None
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"uid": current["uid"]}, {"$set": updates}, upsert=True)
    doc = await db.users.find_one({"uid": current["uid"]})
    return user_to_profile(doc, email_verified=claims_email_verified(current.get("claims") or {}))


@router.get("/api/users/{uid}", response_model=ProfileOut)
async def get_user_by_uid(uid: str, current=Depends(get_current_user)):
    """Public profile view of any user. Email is stripped unless it's the
    caller's own record. Fields marked private in the user's `privacy` map
    are also stripped for non-self queries."""
    db = get_db()
    doc = await db.users.find_one({"uid": uid})
    if not doc:
        raise HTTPException(status_code=404, detail="Player not found")
    is_self = uid == current["uid"]
    profile = user_to_profile(doc)
    if not is_self:
        profile.email = None
        profile.emailVerified = False
        strip_private_fields(profile)
    return profile
