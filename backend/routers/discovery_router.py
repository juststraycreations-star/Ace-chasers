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

    out: list[DiscoveryProfile] = []
    for doc in docs:
        base = user_to_profile(doc)
        strip_private_fields(base)
        post = await get_latest_public_post(doc["uid"])
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
