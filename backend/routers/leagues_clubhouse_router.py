"""League Clubhouse content endpoints — announcements, feed posts, stories,
and lost & found. Extracted out of the 1,800-line `leagues_router.py` as
the first phase of a phased refactor into per-domain submodules.

All endpoints attach to the SAME `api_router` instance owned by
`leagues_router.py` so the URL surface and mounting semantics do not
change; `server.py` still only mounts the leagues router once.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request
from pydantic import BaseModel

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
class FeedPostCreate(BaseModel):
    body: str
    title: Optional[str] = None


@api_router.post("/leagues/{league_id}/feed")
async def create_feed_post(league_id: str, payload: FeedPostCreate, request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    p = FeedPost(league_id=league_id, kind="post", title=payload.title, body=payload.body,
                  author_id=user.user_id, author_name=user.name, author_picture=user.picture)
    await db.feed_posts.insert_one(p.model_dump())
    return p.model_dump()


@api_router.get("/leagues/{league_id}/feed")
async def list_feed(league_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    return await db.feed_posts.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
