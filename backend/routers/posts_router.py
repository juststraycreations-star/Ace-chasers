"""Feed / Posts routes: GET /api/feed, POST /api/posts, DELETE /api/posts/{id}."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import cloud_storage
from db import get_db
from firebase_auth import get_current_user
from models import PostAuthor, PostOut
from posts import (
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    MIME_TO_EXT,
    UPLOAD_DIR,
    create_post,
    delete_post,
    list_feed,
    sniff_image_mime,
    sniff_video_mime,
)


router = APIRouter()


POST_BODY_MAX = 1000
FEED_PAGE_SIZE = 20


async def _hydrate_post(post: dict, viewer_uid: str) -> PostOut:
    db = get_db()
    author = await db.users.find_one({"uid": post["author_uid"]})
    author_obj = PostAuthor(
        uid=post["author_uid"],
        name=(author or {}).get("name"),
        profilePictureUrl=(author or {}).get("profilePictureUrl"),
    )
    image_url = None
    if post.get("image_path"):
        img = post["image_path"]
        # Cloudinary URLs are stored verbatim; legacy disk uploads are bare
        # filenames that need the StaticFiles mount prefix.
        image_url = img if img.startswith("http") else f"/api/uploads/{img}"
    video_url = None
    if post.get("video_path"):
        vid = post["video_path"]
        video_url = vid if vid.startswith("http") else f"/api/uploads/{vid}"
    return PostOut(
        id=post["id"],
        body=post.get("body", ""),
        image_url=image_url,
        video_url=video_url,
        visibility=post.get("visibility", "public"),
        created_at=post.get("created_at", ""),
        author=author_obj,
        is_mine=post["author_uid"] == viewer_uid,
    )


@router.get("/api/feed")
async def get_feed(
    before: Optional[str] = None,
    limit: int = FEED_PAGE_SIZE,
    current=Depends(get_current_user),
):
    """Cursor-paginated feed. `before` is the ISO `created_at` of the last
    item from the previous page; omit on first call. Response shape:
    `{ posts, next_cursor }` where `next_cursor` is null when there are no
    more posts."""
    limit = max(1, min(limit, 50))
    raw_posts = await list_feed(current["uid"], limit=limit, before=before)
    hydrated = [await _hydrate_post(p, current["uid"]) for p in raw_posts]
    next_cursor = raw_posts[-1]["created_at"] if len(raw_posts) == limit else None
    return {"posts": hydrated, "next_cursor": next_cursor}


@router.post("/api/posts", response_model=PostOut)
async def create_post_endpoint(
    body: str = Form(""),
    visibility: Literal["public", "friends_only"] = Form("public"),
    image: Optional[UploadFile] = File(default=None),
    media: Optional[UploadFile] = File(default=None),
    current=Depends(get_current_user),
):
    body = (body or "").strip()
    upload = media if (media is not None and media.filename) else image
    if not body and (upload is None or not upload.filename):
        raise HTTPException(
            status_code=400,
            detail="Post must include text, a photo, or a video",
        )
    if len(body) > POST_BODY_MAX:
        raise HTTPException(
            status_code=400, detail=f"Post text capped at {POST_BODY_MAX} characters"
        )

    image_filename: Optional[str] = None
    video_filename: Optional[str] = None
    if upload is not None and upload.filename:
        data = await upload.read()
        # Sniff image first (cheap), then video. Reject anything else.
        real_mime = sniff_image_mime(data)
        is_video = False
        if real_mime is None:
            real_mime = sniff_video_mime(data)
            is_video = real_mime is not None
        if real_mime is None:
            raise HTTPException(
                status_code=400,
                detail="File is not a supported image (jpeg/png/webp/gif) or video (mp4/webm/mov)",
            )
        if is_video:
            if len(data) > MAX_VIDEO_BYTES:
                raise HTTPException(status_code=400, detail="Video exceeds 25MB limit")
        else:
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")
        ext = MIME_TO_EXT[real_mime]
        prefix = "vid" if is_video else "img"
        base = f"{prefix}-{current['uid'].replace('/', '_')}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}"

        if cloud_storage.is_enabled():
            res = cloud_storage.upload_bytes(
                data,
                folder="acechasers/post",
                public_id=base,
                resource_type="video" if is_video else "image",
            )
            stored = res["secure_url"]
        else:
            fname = f"{base}.{ext}"
            dest = os.path.join(UPLOAD_DIR, fname)
            with open(dest, "wb") as f:
                f.write(data)
            stored = fname

        if is_video:
            video_filename = stored
        else:
            image_filename = stored

    post = await create_post(
        author_uid=current["uid"],
        body=body,
        visibility=visibility,
        image_path=image_filename,
        video_path=video_filename,
    )
    return await _hydrate_post(post, current["uid"])


@router.delete("/api/posts/{post_id}")
async def delete_post_endpoint(post_id: str, current=Depends(get_current_user)):
    ok = await delete_post(post_id, current["uid"])
    if not ok:
        raise HTTPException(status_code=404, detail="Post not found or not yours")
    return {"ok": True}
