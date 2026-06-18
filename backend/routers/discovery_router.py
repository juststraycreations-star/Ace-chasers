"""GET /api/discovery — cursor-paginated list of swipe candidates."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from db import get_db
from deps import strip_private_fields, user_to_profile
from firebase_auth import get_current_user
from models import DiscoveryPage, DiscoveryProfile, RecentPost
from posts import get_latest_public_post


router = APIRouter()


DISCOVERY_PAGE_SIZE = 24


@router.get("/api/discovery", response_model=DiscoveryPage)
async def discovery(
    before: Optional[str] = None,
    limit: int = DISCOVERY_PAGE_SIZE,
    current=Depends(get_current_user),
):
    """Cursor-paginated list of candidate players. `before` is the
    `created_at` ISO of the last player from the previous page (exclusive).
    Players the caller has already swiped on are filtered server-side."""
    limit = max(1, min(limit, 50))
    db = get_db()
    swiped_cursor = db.swipes.find({"from_uid": current["uid"]}, {"to_uid": 1})
    swiped_uids = [d["to_uid"] async for d in swiped_cursor]
    exclude = set(swiped_uids + [current["uid"]])

    query: dict = {"uid": {"$nin": list(exclude)}}
    if before:
        query["created_at"] = {"$lt": before}

    docs: list[dict] = []
    cursor = db.users.find(query).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        docs.append(doc)

    # Batch-fetch latest public post per user (1 query instead of N).
    # Cap the result to give each user a fair chance to surface their
    # latest post (rough heuristic: 5 posts per user is plenty since we
    # only keep the first one we see per author).
    uids = [d["uid"] for d in docs]
    latest_post_by_uid: dict[str, dict] = {}
    if uids:
        post_cap = max(len(uids) * 5, 100)
        posts_cursor = db.posts.find(
            {
                "author_uid": {"$in": uids},
                "visibility": "public",
                "kind": {"$ne": "disc_review"},
            }
        ).sort("created_at", -1).limit(post_cap)
        async for p in posts_cursor:
            uid = p["author_uid"]
            if uid not in latest_post_by_uid:
                latest_post_by_uid[uid] = p

    out: list[DiscoveryProfile] = []
    for doc in docs:
        base = user_to_profile(doc)
        strip_private_fields(base)
        post = latest_post_by_uid.get(doc["uid"])
        recent = None
        if post:
            recent = RecentPost(
                id=post["id"],
                body=post.get("body") or "",
                created_at=post.get("created_at") or "",
                has_image=bool(post.get("image_path")),
            )
        out.append(DiscoveryProfile(**base.model_dump(), recent_post=recent))

    next_cursor = docs[-1].get("created_at") if len(docs) == limit and docs else None
    return DiscoveryPage(players=out, next_cursor=next_cursor)
