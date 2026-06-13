"""Posts collection + helpers.

A post is { id, author_uid, body, image_path?, visibility ('public'|'friends_only'), created_at }.
Image files are stored on disk under /app/backend/uploads/ and exposed via
/api/uploads/<filename> by the StaticFiles mount in server.py.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from db import get_db

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_indexes() -> None:
    db = get_db()
    await db.posts.create_index([("author_uid", 1), ("created_at", -1)])
    await db.posts.create_index([("visibility", 1), ("created_at", -1)])
    await db.posts.create_index("created_at")


async def get_friend_uids(uid: str) -> list[str]:
    """A friendship exists when BOTH users in a match doc are present in the
    `friended_by` array."""
    db = get_db()
    out: list[str] = []
    async for m in db.matches.find({"friended_by": uid}):
        friended = m.get("friended_by") or []
        other = m["user_b"] if m["user_a"] == uid else m["user_a"]
        if other in friended:
            out.append(other)
    return out


async def create_post(
    *,
    author_uid: str,
    body: str,
    visibility: str,
    image_path: Optional[str] = None,
) -> dict:
    db = get_db()
    doc = {
        "id": secrets.token_urlsafe(12),
        "author_uid": author_uid,
        "body": body.strip(),
        "image_path": image_path,
        "visibility": visibility,
        "created_at": _now_iso(),
    }
    await db.posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_feed(viewer_uid: str, limit: int = 50) -> list[dict]:
    db = get_db()
    friends = await get_friend_uids(viewer_uid)

    visibility_filter = {
        "$or": [
            {"author_uid": viewer_uid},
            {"visibility": "public"},
            {"visibility": "friends_only", "author_uid": {"$in": friends}},
        ]
    }

    posts = []
    async for p in db.posts.find(visibility_filter).sort("created_at", -1).limit(limit):
        p.pop("_id", None)
        posts.append(p)
    return posts


async def delete_post(post_id: str, author_uid: str) -> bool:
    db = get_db()
    res = await db.posts.delete_one({"id": post_id, "author_uid": author_uid})
    return res.deleted_count == 1


async def get_post(post_id: str) -> Optional[dict]:
    db = get_db()
    doc = await db.posts.find_one({"id": post_id})
    if doc:
        doc.pop("_id", None)
    return doc
