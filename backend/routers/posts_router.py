"""Feed / Posts routes: GET /api/feed, POST /api/posts, DELETE /api/posts/{id},
POST /api/posts/{id}/nice (toggle), GET/POST /api/posts/{id}/comments."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import cloud_storage
from db import get_db
from firebase_auth import get_current_user
from models import CommentIn, CommentOut, PostAuthor, PostOut
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
        image_url = img if img.startswith("http") else f"/api/uploads/{img}"
    video_url = None
    if post.get("video_path"):
        vid = post["video_path"]
        video_url = vid if vid.startswith("http") else f"/api/uploads/{vid}"
    nice_count = await db.post_likes.count_documents(
        {"post_id": post["id"], "value": {"$ne": "down"}}
    )
    down_count = await db.post_likes.count_documents(
        {"post_id": post["id"], "value": "down"}
    )
    my_reaction = await db.post_likes.find_one(
        {"post_id": post["id"], "user_uid": viewer_uid}
    )
    liked_by_me = bool(my_reaction and my_reaction.get("value") != "down")
    disliked_by_me = bool(my_reaction and my_reaction.get("value") == "down")
    comment_count = await db.post_comments.count_documents({"post_id": post["id"]})
    return PostOut(
        id=post["id"],
        body=post.get("body", ""),
        image_url=image_url,
        video_url=video_url,
        visibility=post.get("visibility", "public"),
        kind=post.get("kind", "post"),
        created_at=post.get("created_at", ""),
        author=author_obj,
        is_mine=post["author_uid"] == viewer_uid,
        nice_count=nice_count,
        down_count=down_count,
        liked_by_me=liked_by_me,
        disliked_by_me=disliked_by_me,
        comment_count=comment_count,
    )


@router.get("/api/feed")
async def get_feed(
    before: Optional[str] = None,
    limit: int = FEED_PAGE_SIZE,
    kind: Optional[Literal["post", "disc_review"]] = None,
    current=Depends(get_current_user),
):
    """Cursor-paginated feed. Pass `kind=disc_review` for the Bag Check
    feed, otherwise returns the regular social feed."""
    limit = max(1, min(limit, 50))
    raw_posts = await list_feed(current["uid"], limit=limit, before=before, kind=kind)
    hydrated = [await _hydrate_post(p, current["uid"]) for p in raw_posts]
    next_cursor = raw_posts[-1]["created_at"] if len(raw_posts) == limit else None
    return {"posts": hydrated, "next_cursor": next_cursor}


@router.post("/api/posts", response_model=PostOut)
async def create_post_endpoint(
    body: str = Form(""),
    visibility: Literal["public", "friends_only"] = Form("public"),
    kind: Literal["post", "disc_review"] = Form("post"),
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
        kind=kind,
    )
    return await _hydrate_post(post, current["uid"])


@router.delete("/api/posts/{post_id}")
async def delete_post_endpoint(post_id: str, current=Depends(get_current_user)):
    ok = await delete_post(post_id, current["uid"])
    if not ok:
        raise HTTPException(status_code=404, detail="Post not found or not yours")
    return {"ok": True}



# --- Nice (likes) + comments -----------------------------------------------

@router.post("/api/posts/{post_id}/nice")
async def toggle_nice(post_id: str, current=Depends(get_current_user)):
    """Legacy toggle: switches a 'nice' (up) reaction on/off. Kept for the
    regular feed posts."""
    return await _set_reaction(post_id, current["uid"], "up")


@router.post("/api/posts/{post_id}/react")
async def react(
    post_id: str,
    value: Literal["up", "down"],
    current=Depends(get_current_user),
):
    """Set a thumbs-up or thumbs-down reaction. Clicking the same value
    again removes it; clicking the opposite value switches it."""
    return await _set_reaction(post_id, current["uid"], value)


async def _set_reaction(post_id: str, user_uid: str, value: str) -> dict:
    db = get_db()
    existing = await db.post_likes.find_one({"post_id": post_id, "user_uid": user_uid})
    if existing and existing.get("value", "up") == value:
        # Same value tapped twice -> remove.
        await db.post_likes.delete_one({"_id": existing["_id"]})
    elif existing:
        await db.post_likes.update_one(
            {"_id": existing["_id"]}, {"$set": {"value": value}}
        )
    else:
        await db.post_likes.insert_one(
            {
                "post_id": post_id,
                "user_uid": user_uid,
                "value": value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    nice_count = await db.post_likes.count_documents(
        {"post_id": post_id, "value": {"$ne": "down"}}
    )
    down_count = await db.post_likes.count_documents(
        {"post_id": post_id, "value": "down"}
    )
    my = await db.post_likes.find_one({"post_id": post_id, "user_uid": user_uid})
    return {
        "liked_by_me": bool(my and my.get("value") != "down"),
        "disliked_by_me": bool(my and my.get("value") == "down"),
        "nice_count": nice_count,
        "down_count": down_count,
    }


@router.get("/api/posts/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(post_id: str, current=Depends(get_current_user)):
    db = get_db()
    out: list[CommentOut] = []
    async for c in db.post_comments.find({"post_id": post_id}).sort("created_at", 1).limit(500):
        author = await db.users.find_one({"uid": c["author_uid"]})
        out.append(
            CommentOut(
                id=c["id"],
                post_id=c["post_id"],
                body=c["body"],
                created_at=c["created_at"],
                author=PostAuthor(
                    uid=c["author_uid"],
                    name=(author or {}).get("name"),
                    profilePictureUrl=(author or {}).get("profilePictureUrl"),
                ),
                is_mine=c["author_uid"] == current["uid"],
            )
        )
    return out


@router.post("/api/posts/{post_id}/comments", response_model=CommentOut)
async def add_comment(
    post_id: str, payload: CommentIn, current=Depends(get_current_user)
):
    db = get_db()
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    doc = {
        "id": secrets.token_urlsafe(10),
        "post_id": post_id,
        "author_uid": current["uid"],
        "body": body,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.post_comments.insert_one(doc)
    author = await db.users.find_one({"uid": current["uid"]})
    return CommentOut(
        id=doc["id"],
        post_id=post_id,
        body=body,
        created_at=doc["created_at"],
        author=PostAuthor(
            uid=current["uid"],
            name=(author or {}).get("name"),
            profilePictureUrl=(author or {}).get("profilePictureUrl"),
        ),
        is_mine=True,
    )


@router.delete("/api/posts/{post_id}/comments/{comment_id}")
async def delete_comment(
    post_id: str, comment_id: str, current=Depends(get_current_user)
):
    db = get_db()
    res = await db.post_comments.delete_one(
        {"id": comment_id, "post_id": post_id, "author_uid": current["uid"]}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Comment not found or not yours")
    return {"ok": True}
