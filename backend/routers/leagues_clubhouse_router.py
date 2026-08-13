"""League Clubhouse content endpoints — announcements, feed posts, stories,
and lost & found. Extracted out of the 1,800-line `leagues_router.py` as
the first phase of a phased refactor into per-domain submodules.

All endpoints attach to the SAME `api_router` instance owned by
`leagues_router.py` so the URL surface and mounting semantics do not
change; `server.py` still only mounts the leagues router once.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

# All of these are defined in leagues_router.py — we reuse the same
# router instance + helpers so we do not double-register or double-shim
# the auth/db plumbing.
from .leagues_router import (
    api_router,
    db,
    get_current_user,
    _require_member,
    ws_manager,
    Announcement,
    LostFound,
    StoryPost,
    FeedPost,
)


# ============= ANNOUNCEMENTS =============
class AnnouncementCreate(BaseModel):
    title: str
    body: str
    urgent: bool = False


@api_router.post("/leagues/{league_id}/announcements")
async def create_announcement(league_id: str, payload: AnnouncementCreate, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    a = Announcement(league_id=league_id, title=payload.title, body=payload.body,
                     urgent=payload.urgent, author_id=user.user_id, author_name=user.name)
    await db.announcements.insert_one(a.model_dump())
    await ws_manager.broadcast(f"league:{league_id}", {"type": "announcement", "announcement": a.model_dump()})
    return a.model_dump()


@api_router.get("/leagues/{league_id}/announcements")
async def list_announcements(league_id: str, request: Request,
                              session_token: Optional[str] = Cookie(None),
                              authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.announcements.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api_router.delete("/announcements/{announcement_id}")
async def delete_announcement(announcement_id: str, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    a = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    m = await _require_member(a["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    await db.announcements.delete_one({"id": announcement_id})
    return {"ok": True}


# ============= LOST & FOUND =============
class LostFoundCreate(BaseModel):
    title: str
    description: str
    image_path: Optional[str] = None


@api_router.post("/leagues/{league_id}/lost-found")
async def create_lost_found(league_id: str, payload: LostFoundCreate, request: Request,
                              session_token: Optional[str] = Cookie(None),
                              authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    lf = LostFound(league_id=league_id, title=payload.title, description=payload.description,
                    image_path=payload.image_path, author_id=user.user_id, author_name=user.name)
    await db.lost_found.insert_one(lf.model_dump())
    return lf.model_dump()


@api_router.get("/leagues/{league_id}/lost-found")
async def list_lost_found(league_id: str, request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.lost_found.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api_router.patch("/lost-found/{item_id}/resolve")
async def resolve_lost_found(item_id: str, request: Request,
                               session_token: Optional[str] = Cookie(None),
                               authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    item = await db.lost_found.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    await _require_member(item["league_id"], user.user_id)
    await db.lost_found.update_one({"id": item_id}, {"$set": {"resolved": True}})
    return {"ok": True}


# ============= STORIES =============
class StoryCreate(BaseModel):
    image_path: str
    caption: Optional[str] = ""


@api_router.post("/leagues/{league_id}/stories")
async def create_story(league_id: str, payload: StoryCreate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    s = StoryPost(league_id=league_id, image_path=payload.image_path, caption=payload.caption or "",
                   author_id=user.user_id, author_name=user.name, author_picture=user.picture)
    await db.stories.insert_one(s.model_dump())
    return s.model_dump()


@api_router.get("/leagues/{league_id}/stories")
async def list_stories(league_id: str, request: Request,
                         session_token: Optional[str] = Cookie(None),
                         authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    # Show stories from the last 48 hours
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    return await db.stories.find({"league_id": league_id, "created_at": {"$gte": cutoff}},
                                   {"_id": 0}).sort("created_at", -1).to_list(100)


# ============= LEAGUE FEED (member wall) =============
class FeedMediaItem(BaseModel):
    kind: Literal["image", "video"]
    path: str
    poster: Optional[str] = None


class FeedPostCreate(BaseModel):
    body: str = ""
    title: Optional[str] = None
    # Legacy single-item fields (kept for backward-compat). New callers
    # should send `media` as an ordered list instead.
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    video_poster: Optional[str] = None
    # New in iteration 51: an arbitrary ordered list of attachments.
    # Each item is `{ kind: "image"|"video", path, poster? }`. Payloads
    # that mix `media` and legacy fields are normalized server-side.
    media: List[FeedMediaItem] = Field(default_factory=list)


@api_router.post("/leagues/{league_id}/feed")
async def create_feed_post(league_id: str, payload: FeedPostCreate, request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    body = (payload.body or "").strip()
    # Normalize incoming media: prefer explicit `media[]`, but fold any
    # legacy image_path/video_path into the front of the list so a client
    # that still sends the old shape keeps working.
    media: List[Dict[str, Any]] = []
    if payload.image_path:
        media.append({"kind": "image", "path": payload.image_path})
    if payload.video_path:
        media.append({"kind": "video", "path": payload.video_path,
                      "poster": payload.video_poster})
    for m in payload.media:
        media.append(m.model_dump())
    has_media = bool(media)
    if not body and not has_media:
        raise HTTPException(status_code=400, detail="Post must include text or media")
    # Populate legacy single-item fields from the first-of-kind so old
    # feed renderers (mobile clients, share-cards) still work.
    first_image = next((m for m in media if m["kind"] == "image"), None)
    first_video = next((m for m in media if m["kind"] == "video"), None)
    p = FeedPost(
        league_id=league_id, kind="post", title=payload.title, body=body,
        author_id=user.user_id, author_name=user.name, author_picture=user.picture,
        image_path=(first_image or {}).get("path"),
        video_path=(first_video or {}).get("path"),
        video_poster=(first_video or {}).get("poster"),
        media=media,
    )
    await db.feed_posts.insert_one(p.model_dump())
    return p.model_dump()


@api_router.get("/leagues/{league_id}/feed")
async def list_feed(league_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    # Hide moderator-deleted posts from everyone except the director,
    # who can still see them (greyed out in the UI) for audit.
    lg = await db.leagues.find_one(
        {"id": league_id}, {"_id": 0, "director_id": 1}
    )
    is_director = bool(lg and lg.get("director_id") == user.user_id)
    q: dict = {"league_id": league_id}
    if not is_director:
        q["hidden"] = {"$ne": True}
    return await db.feed_posts.find(q, {"_id": 0}).sort([("pinned", -1), ("created_at", -1)]).to_list(200)
