"""Auth + profile routes: /api/auth/sync, /api/users/me, /api/users/{uid}."""
from __future__ import annotations

import logging
import re
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


log = logging.getLogger("auth_router")
router = APIRouter()

# Shared with server._backfill_first_run_flag(). Emails matching this
# pattern belong to the testing agent / QA and must NEVER count toward
# — or be awarded — the founding-member badge.
_TEST_EMAIL_RE = re.compile(
    r"(^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner))|(@example\.com$)",
    re.IGNORECASE,
)


def _is_test_email(email: str | None) -> bool:
    if not email:
        return False
    return bool(_TEST_EMAIL_RE.search(email))


@router.post("/api/auth/sync", response_model=ProfileOut)
async def auth_sync(
    payload: AuthSyncIn = Body(default_factory=AuthSyncIn),
    current=Depends(get_current_user),
):
    """Idempotently upsert the user record for the caller. New users may need
    to redeem an invite code when REQUIRE_INVITE is enabled. Existing users
    always pass through (no retroactive gating).

    Hardened Feb 2026: EVERY code path is wrapped so we NEVER leak an
    unhandled exception. An empty response body was causing Cloudflare to
    return 520 to the browser, which then poisoned the client's service
    worker and locked users out. HTTPExceptions still propagate cleanly.
    """
    try:
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

        # Founding-member logic: the first 40 real (non-test-email) rows
        # ever created carry first_run=true. Frozen at insert time.
        is_first_run = False
        if is_new_user:
            FOUNDING_LIMIT = 40
            current_email = current.get("email")
            if not _is_test_email(current_email):
                # Defensive: if the founding-count query fails (Mongo
                # hiccup) we still admit the user. They just don't get
                # the badge on this specific signup; the startup back-
                # fill will award it on the next boot.
                try:
                    test_email_re = r"(^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner))|(@example\.com$)"
                    existing_count = await db.users.count_documents({
                        "$and": [
                            {"$or": [{"is_seed": {"$exists": False}}, {"is_seed": False}]},
                            {"$or": [
                                {"email": None},
                                {"email": ""},
                                {"email": {"$exists": False}},
                                {"email": {"$not": {"$regex": test_email_re, "$options": "i"}}},
                            ]},
                        ]
                    })
                    is_first_run = existing_count < FOUNDING_LIMIT
                except Exception:  # noqa: BLE001
                    log.exception("founding-member count failed — deferring to backfill")

        set_on_insert = {
            "uid": current["uid"],
            "created_at": now,
            "is_seed": False,
            "interests": ["casual play"],
            "skillLevel": "Beginner",
            "bio": "New to Ace Chasers!",
            "first_run": is_first_run,
            "has_dismissed_first_run_modal": False,
            "has_viewed_leagues_feature": False,
        }
        if current.get("name"):
            set_on_insert["name"] = current["name"]
        if current.get("picture"):
            set_on_insert["profilePictureUrl"] = current["picture"]

        update = {
            "$setOnInsert": set_on_insert,
            "$set": {
                "email": current.get("email"),
                "email_verified": email_verified,
                "updated_at": now,
            },
        }
        await db.users.update_one({"uid": current["uid"]}, update, upsert=True)

        doc = await db.users.find_one({"uid": current["uid"]})
        if not doc:
            # Should be impossible after an upsert, but if it happens we
            # emit a synthetic profile rather than a 500 with empty body.
            log.error("auth_sync: doc missing after upsert for uid=%s", current["uid"])
            return ProfileOut(
                uid=current["uid"],
                email=current.get("email"),
                emailVerified=email_verified,
            )
        return user_to_profile(doc, email_verified=email_verified)
    except HTTPException:
        # Legitimate 4xx (invite required, forbidden, etc.) — propagate.
        raise
    except Exception as exc:  # noqa: BLE001
        # Anything else becomes a clean JSON 500. Never leak an empty body.
        log.exception("auth_sync crashed for uid=%s", (current or {}).get("uid"))
        raise HTTPException(
            status_code=500,
            detail=f"auth_sync failed: {type(exc).__name__}",
        )


@router.post("/api/users/me/dismiss-first-run", response_model=ProfileOut)
async def dismiss_first_run_modal(current=Depends(get_current_user)):
    """Idempotently mark the founding-member congrats modal as dismissed so
    it never renders for this user again."""
    db = get_db()
    await db.users.update_one(
        {"uid": current["uid"]},
        {"$set": {"has_dismissed_first_run_modal": True,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    doc = await db.users.find_one({"uid": current["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return user_to_profile(doc, email_verified=claims_email_verified(current.get("claims") or {}))


@router.post("/api/users/me/dismiss-leagues-feature", response_model=ProfileOut)
async def dismiss_leagues_feature_pulse(current=Depends(get_current_user)):
    """Mark the "Leagues are live" nav announcement as seen so the amber
    pulse dot disappears for this user."""
    db = get_db()
    await db.users.update_one(
        {"uid": current["uid"]},
        {"$set": {"has_viewed_leagues_feature": True,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    doc = await db.users.find_one({"uid": current["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return user_to_profile(doc, email_verified=claims_email_verified(current.get("claims") or {}))


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


@router.post("/api/users/me/dm-terms/agree", response_model=ProfileOut)
async def agree_dm_terms(current=Depends(get_current_user)):
    """First-time DM Fair Play terms agreement. Persists dm_terms_agreed_at on
    the user's profile document so the DM invite prompt only appears once
    per user across all league and non-league DM surfaces."""
    db = get_db()
    doc = await db.users.find_one({"uid": current["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found — call /api/auth/sync first")
    if not doc.get("dm_terms_agreed_at"):
        now = datetime.now(timezone.utc).isoformat()
        await db.users.update_one(
            {"uid": current["uid"]},
            {"$set": {"dm_terms_agreed_at": now}},
        )
        doc["dm_terms_agreed_at"] = now
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
