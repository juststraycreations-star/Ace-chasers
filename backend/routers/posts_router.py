"""Feed / Posts routes: GET /api/feed, POST /api/posts, DELETE /api/posts/{id},
POST /api/posts/{id}/nice (toggle), GET/POST /api/posts/{id}/comments."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
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
    list_user_posts,
    sniff_image_mime,
    sniff_video_mime,
)


router = APIRouter()


POST_BODY_MAX = 1000
FEED_PAGE_SIZE = 20


async def _hydrate_post(post: dict, viewer_uid: str) -> PostOut:
    """Single-post hydration. Thin wrapper around the batch helper so
    callers handling one post (e.g. create_post, get_top_niced) don't
    duplicate the batching logic."""
    out = await _hydrate_posts([post], viewer_uid)
    return out[0]


async def _hydrate_posts(posts: list[dict], viewer_uid: str) -> list[PostOut]:
    """Hydrate a list of raw post dicts into PostOut models using batched
    queries — 5 DB round-trips total regardless of how many posts are in
    the list (authors, nice counts, down counts, viewer reactions,
    comment counts). Replaces the prior N+1 pattern."""
    if not posts:
        return []
    db = get_db()
    post_ids = [p["id"] for p in posts]
    author_uids = list({p["author_uid"] for p in posts})

    # Authors — one query for every distinct author on the page.
    authors_by_uid: dict[str, dict] = {}
    if author_uids:
        async for u in db.users.find(
            {"uid": {"$in": author_uids}},
            {"uid": 1, "name": 1, "profilePictureUrl": 1, "_id": 0},
        ):
            authors_by_uid[u["uid"]] = u

    # Nice / Down counts — one aggregation grouped by post_id.
    nice_by_post: dict[str, int] = {pid: 0 for pid in post_ids}
    down_by_post: dict[str, int] = {pid: 0 for pid in post_ids}
    async for row in db.post_likes.aggregate(
        [
            {"$match": {"post_id": {"$in": post_ids}}},
            {
                "$group": {
                    "_id": {"post_id": "$post_id", "value": "$value"},
                    "n": {"$sum": 1},
                }
            },
        ]
    ):
        pid = row["_id"]["post_id"]
        if row["_id"].get("value") == "down":
            down_by_post[pid] = row["n"]
        else:
            nice_by_post[pid] = nice_by_post.get(pid, 0) + row["n"]

    # Viewer's reactions across this page — one find.
    my_reactions: dict[str, str] = {}
    async for r in db.post_likes.find(
        {"post_id": {"$in": post_ids}, "user_uid": viewer_uid},
        {"post_id": 1, "value": 1, "_id": 0},
    ):
        my_reactions[r["post_id"]] = r.get("value", "")

    # Comment counts — one aggregation grouped by post_id.
    comment_count_by_post: dict[str, int] = {pid: 0 for pid in post_ids}
    async for row in db.post_comments.aggregate(
        [
            {"$match": {"post_id": {"$in": post_ids}}},
            {"$group": {"_id": "$post_id", "n": {"$sum": 1}}},
        ]
    ):
        comment_count_by_post[row["_id"]] = row["n"]

    out: list[PostOut] = []
    for post in posts:
        author = authors_by_uid.get(post["author_uid"])
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
        my_val = my_reactions.get(post["id"])
        out.append(
            PostOut(
                id=post["id"],
                body=post.get("body", ""),
                image_url=image_url,
                video_url=video_url,
                visibility=post.get("visibility", "public"),
                kind=post.get("kind", "post"),
                created_at=post.get("created_at", ""),
                author=author_obj,
                is_mine=post["author_uid"] == viewer_uid,
                nice_count=nice_by_post.get(post["id"], 0),
                down_count=down_by_post.get(post["id"], 0),
                liked_by_me=bool(my_val and my_val != "down"),
                disliked_by_me=my_val == "down",
                comment_count=comment_count_by_post.get(post["id"], 0),
            )
        )
    return out


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
    hydrated = await _hydrate_posts(raw_posts, current["uid"])
    # Batch-fetch up to 3 most recent comments per post in this page.
    if hydrated:
        await _attach_recent_comments(hydrated, current["uid"])
    next_cursor = raw_posts[-1]["created_at"] if len(raw_posts) == limit else None
    return {"posts": hydrated, "next_cursor": next_cursor}


@router.get("/api/feed/top-niced-this-week", response_model=Optional[PostOut])
async def get_top_niced_this_week(current=Depends(get_current_user)):
    """The single public post with the most 👍 Nice reactions in the past 7
    days. Used by the Feed page's "🏆 Most niced this week" badge. Returns
    null when no qualifying post exists yet."""
    db = get_db()
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pipeline = [
        {"$match": {"value": {"$ne": "down"}, "created_at": {"$gte": one_week_ago}}},
        {
            "$lookup": {
                "from": "posts",
                "localField": "post_id",
                "foreignField": "id",
                "as": "post",
            }
        },
        {"$unwind": "$post"},
        {
            "$match": {
                "post.visibility": "public",
                "post.kind": {"$ne": "disc_review"},
            }
        },
        {"$group": {"_id": "$post_id", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 1},
    ]
    rows = [r async for r in db.post_likes.aggregate(pipeline)]
    if not rows or rows[0]["n"] == 0:
        return None
    raw = await db.posts.find_one({"id": rows[0]["_id"]})
    if not raw:
        return None
    hydrated = await _hydrate_post(raw, current["uid"])
    await _attach_recent_comments([hydrated], current["uid"])
    return hydrated


async def _attach_recent_comments(
    posts: list[PostOut], viewer_uid: str, per_post: int = 3
) -> None:
    """Mutates `posts` in place, populating `recent_comments` (oldest of the
    N newest first, so they read naturally under the post). One aggregation
    query covers every post on the page."""
    if not posts:
        return
    db = get_db()
    post_ids = [p.id for p in posts]
    pipeline = [
        {"$match": {"post_id": {"$in": post_ids}}},
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$post_id",
                "comments": {"$push": "$$ROOT"},
            }
        },
        {
            "$project": {
                "_id": 1,
                "comments": {"$slice": ["$comments", per_post]},
            }
        },
    ]
    grouped: dict[str, list[dict]] = {}
    author_uids: set[str] = set()
    async for row in db.post_comments.aggregate(pipeline):
        # Reverse so the oldest of the slice is first (chronological under post).
        comments = list(reversed(row.get("comments") or []))
        grouped[row["_id"]] = comments
        for c in comments:
            author_uids.add(c["author_uid"])
    authors_by_uid: dict[str, dict] = {}
    if author_uids:
        async for u in db.users.find({"uid": {"$in": list(author_uids)}}):
            authors_by_uid[u["uid"]] = u
    for post in posts:
        bucket = grouped.get(post.id) or []
        post.recent_comments = [
            CommentOut(
                id=c["id"],
                post_id=c["post_id"],
                body=c["body"],
                created_at=c["created_at"],
                author=PostAuthor(
                    uid=c["author_uid"],
                    name=(authors_by_uid.get(c["author_uid"]) or {}).get("name"),
                    profilePictureUrl=(authors_by_uid.get(c["author_uid"]) or {}).get(
                        "profilePictureUrl"
                    ),
                ),
                is_mine=c["author_uid"] == viewer_uid,
            )
            for c in bucket
        ]
    # Hydrate reactions across every preview comment on every post in one go.
    all_previews = [c for post in posts for c in post.recent_comments]
    await _attach_comment_reactions(all_previews, viewer_uid)


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



@router.get("/api/users/{author_uid}/posts", response_model=list[PostOut])
async def get_user_posts(author_uid: str, current=Depends(get_current_user)):
    """All posts authored by the given user that the caller can see. Used by
    the Profile page (their own posts) and PlayerProfile (someone else's)."""
    raw = await list_user_posts(author_uid, current["uid"])
    hydrated = await _hydrate_posts(raw, current["uid"])
    await _attach_recent_comments(hydrated, current["uid"])
    return hydrated


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
    comments = await (
        db.post_comments.find({"post_id": post_id})
        .sort("created_at", 1)
        .limit(500)
        .to_list(length=500)
    )
    author_uids = list({c["author_uid"] for c in comments})
    authors_by_uid: dict[str, dict] = {}
    if author_uids:
        async for u in db.users.find({"uid": {"$in": author_uids}}):
            authors_by_uid[u["uid"]] = u
    out: list[CommentOut] = []
    for c in comments:
        author = authors_by_uid.get(c["author_uid"])
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
    await _attach_comment_reactions(out, current["uid"])
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
    # Cascade: drop any nice/likes on the deleted comment so counts stay sane.
    await db.post_comment_likes.delete_many({"comment_id": comment_id})
    return {"ok": True}


# --- Comment "Nice" reactions ----------------------------------------------

@router.post("/api/posts/{post_id}/comments/{comment_id}/nice")
async def toggle_comment_nice(
    post_id: str, comment_id: str, current=Depends(get_current_user)
):
    """Toggle a 👍 Nice reaction on a comment. Idempotent: tapping again
    removes it. Returns the new nice_count + liked_by_me."""
    db = get_db()
    # Make sure the comment actually exists (defensive — keeps stray likes
    # out of the post_comment_likes collection).
    comment = await db.post_comments.find_one({"id": comment_id, "post_id": post_id})
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    existing = await db.post_comment_likes.find_one(
        {"comment_id": comment_id, "user_uid": current["uid"]}
    )
    if existing:
        await db.post_comment_likes.delete_one({"_id": existing["_id"]})
    else:
        await db.post_comment_likes.insert_one(
            {
                "comment_id": comment_id,
                "user_uid": current["uid"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    nice_count = await db.post_comment_likes.count_documents({"comment_id": comment_id})
    liked_by_me = existing is None  # we just inserted; (existing was None)
    return {"nice_count": nice_count, "liked_by_me": liked_by_me}


async def _attach_comment_reactions(
    comments: list[CommentOut], viewer_uid: str
) -> None:
    """Populate nice_count + liked_by_me on every comment in `comments` using
    one batched count aggregation and one viewer-specific find. Mutates in
    place."""
    if not comments:
        return
    db = get_db()
    comment_ids = [c.id for c in comments]
    # Total nice counts per comment in a single aggregation.
    counts: dict[str, int] = {}
    pipeline = [
        {"$match": {"comment_id": {"$in": comment_ids}}},
        {"$group": {"_id": "$comment_id", "n": {"$sum": 1}}},
    ]
    async for row in db.post_comment_likes.aggregate(pipeline):
        counts[row["_id"]] = row["n"]
    # My own likes (so the heart fills correctly).
    mine: set[str] = set()
    async for row in db.post_comment_likes.find(
        {"comment_id": {"$in": comment_ids}, "user_uid": viewer_uid}
    ):
        mine.add(row["comment_id"])
    for c in comments:
        c.nice_count = counts.get(c.id, 0)
        c.liked_by_me = c.id in mine
