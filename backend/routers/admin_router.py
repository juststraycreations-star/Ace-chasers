"""Admin-only endpoints (protected by X-Admin-Key header)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from deps import require_admin
from invites import create_invite, list_invites, revoke_invite
from models import InviteCreateIn


router = APIRouter()


@router.get("/api/admin/invites")
async def admin_list_invites(_: bool = Depends(require_admin)):
    return await list_invites()


@router.post("/api/admin/invites")
async def admin_create_invite(payload: InviteCreateIn, _: bool = Depends(require_admin)):
    return await create_invite(email=payload.email, expires_at=payload.expires_at)


@router.delete("/api/admin/invites/{code}")
async def admin_revoke_invite(code: str, _: bool = Depends(require_admin)):
    ok = await revoke_invite(code)
    if not ok:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"ok": True}


@router.post("/api/admin/cleanup-seeds")
async def admin_cleanup_seeds(dry_run: bool = True, _: bool = Depends(require_admin)):
    """Delete every seed and @example.* test user (with cascading data).
    Pass `?dry_run=false` to actually delete; default is a dry run that just
    returns counts so you can sanity-check first."""
    db = get_db()
    example_re = re.compile(r"@example\.(com|org|net)$", re.IGNORECASE)
    seed_users = await db.users.find({"is_seed": True}).to_list(length=None)
    test_users = []
    async for u in db.users.find({}):
        if example_re.search(u.get("email") or ""):
            test_users.append(u)
    uids = [u["uid"] for u in seed_users + test_users]
    if not uids:
        return {"dry_run": dry_run, "users": 0, "msg": "Nothing to clean"}

    posts_q = {"author_uid": {"$in": uids}}
    swipes_q = {"$or": [{"from_uid": {"$in": uids}}, {"to_uid": {"$in": uids}}]}
    matches_q = {"$or": [{"user_a": {"$in": uids}}, {"user_b": {"$in": uids}}]}
    fr_q = {"$or": [{"from_uid": {"$in": uids}}, {"to_uid": {"$in": uids}}]}

    if dry_run:
        return {
            "dry_run": True,
            "users": len(uids),
            "seed_users": [u.get("email") or u["uid"] for u in seed_users],
            "test_users": [u.get("email") for u in test_users],
            "posts": await db.posts.count_documents(posts_q),
            "swipes": await db.swipes.count_documents(swipes_q),
            "matches": await db.matches.count_documents(matches_q),
            "friend_requests": await db.friend_requests.count_documents(fr_q),
        }

    r_posts = await db.posts.delete_many(posts_q)
    r_swipes = await db.swipes.delete_many(swipes_q)
    r_matches = await db.matches.delete_many(matches_q)
    r_fr = await db.friend_requests.delete_many(fr_q)
    r_users = await db.users.delete_many({"uid": {"$in": uids}})
    return {
        "dry_run": False,
        "deleted": {
            "users": r_users.deleted_count,
            "posts": r_posts.deleted_count,
            "swipes": r_swipes.deleted_count,
            "matches": r_matches.deleted_count,
            "friend_requests": r_fr.deleted_count,
        },
    }
