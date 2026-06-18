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
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_VIDEO_BYTES = 25 * 1024 * 1024  # 25MB cap for short videos


# Validated MIME -> safe extension. The client-supplied filename extension is
# ignored to prevent an attacker from uploading a `.html` masquerading as an
# image and getting it served back by the StaticFiles mount.
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


def sniff_image_mime(data: bytes) -> Optional[str]:
    """Inspect magic bytes to determine the real image MIME type.
    Returns None for unrecognized formats."""
    if len(data) < 12:
        return None
    if data[0:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[0:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[0:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sniff_video_mime(data: bytes) -> Optional[str]:
    """Detect mp4/webm/mov by inspecting container magic bytes.

    For ISO-BMFF (mp4/mov) we enforce a brand whitelist: the 4 bytes at
    offset 8 must be one of the known "safe" major brands. This rejects
    fragmented or container formats that share the `ftyp` header but are
    not standard mp4/mov (e.g. .3gp, .heic, .heif, .avif, .crx, .f4v).
    """
    if len(data) < 16:
        return None
    # mp4/mov - ISO base media file format: bytes 4..8 == 'ftyp'
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        # QuickTime
        if brand in (b"qt  ",):
            return "video/quicktime"
        # Standard MP4 brands.
        SAFE_MP4_BRANDS = {
            b"isom",  # ISO Base Media file format
            b"iso2",
            b"iso4",
            b"iso5",
            b"iso6",
            b"mp41",
            b"mp42",
            b"avc1",
            b"M4V ",  # iTunes M4V
            b"dash",
            b"mmp4",
        }
        if brand in SAFE_MP4_BRANDS:
            return "video/mp4"
        return None  # unknown brand -> reject
    # webm/matroska - EBML header 1A 45 DF A3
    if data[0:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


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
    async for m in db.matches.find({"friended_by": uid}).limit(500):
        friended = m.get("friended_by") or []
        other = m["user_b"] if m["user_a"] == uid else m["user_a"]
        if other in friended:
            out.append(other)
    return out


async def get_latest_public_post(author_uid: str) -> Optional[dict]:
    """Most recent public post by `author_uid`, or None."""
    db = get_db()
    doc = await db.posts.find_one(
        {"author_uid": author_uid, "visibility": "public"},
        sort=[("created_at", -1)],
    )
    if doc:
        doc.pop("_id", None)
    return doc


async def create_post(
    *,
    author_uid: str,
    body: str,
    visibility: str,
    image_path: Optional[str] = None,
    video_path: Optional[str] = None,
    kind: str = "post",
) -> dict:
    db = get_db()
    doc = {
        "id": secrets.token_urlsafe(12),
        "author_uid": author_uid,
        "body": body.strip(),
        "image_path": image_path,
        "video_path": video_path,
        "visibility": visibility,
        "kind": kind,
        "created_at": _now_iso(),
    }
    await db.posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_feed(
    viewer_uid: str,
    limit: int = 20,
    before: Optional[str] = None,
    kind: Optional[str] = None,
) -> list[dict]:
    """Return posts visible to the viewer, newest first, paginated by an
    ISO `created_at` cursor (`before` excluded). Pass `kind="disc_review"`
    to filter the Bag Check feed; pass `kind="post"` (or None) for the
    regular social feed."""
    db = get_db()
    friends = await get_friend_uids(viewer_uid)

    query: dict = {
        "$or": [
            {"author_uid": viewer_uid},
            {"visibility": "public"},
            {"visibility": "friends_only", "author_uid": {"$in": friends}},
        ]
    }
    if kind == "disc_review":
        query["kind"] = "disc_review"
    else:
        # Legacy rows have no `kind` field; treat them as regular posts.
        query["kind"] = {"$ne": "disc_review"}
    if before:
        query["created_at"] = {"$lt": before}

    posts = []
    async for p in db.posts.find(query).sort("created_at", -1).limit(limit):
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
