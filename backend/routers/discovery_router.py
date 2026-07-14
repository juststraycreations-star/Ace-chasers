"""GET /api/discovery — cursor-paginated list of swipe candidates."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends

from db import get_db
from deps import strip_private_fields, user_to_profile
from firebase_auth import get_current_user
from geocode import geocode_location, haversine_miles
from models import DiscoveryPage, DiscoveryProfile, RecentPost
from posts import get_latest_public_post


router = APIRouter()


# Discovery default page size. Bumped from 24 → 100 so all users on a
# launching / small-community app appear on the first fetch without
# needing to click "Load more". The endpoint still supports pagination
# via `before` for when the user base grows past this.
DISCOVERY_PAGE_SIZE = 100
# When the caller passes radius_miles, we widen the underlying scan so that
# the haversine filter still returns a full page on dense regions.
RADIUS_SCAN_MULTIPLIER = 6


async def _viewer_coords(uid: str) -> Optional[tuple[float, float]]:
    db = get_db()
    me = await db.users.find_one({"uid": uid})
    if not me:
        return None
    if me.get("lat") is not None and me.get("lng") is not None:
        return float(me["lat"]), float(me["lng"])
    # Backfill from the caller's saved free-text location if it wasn't
    # geocoded yet (legacy user docs predating the geocode integration).
    loc = (me.get("location") or "").strip()
    if not loc:
        return None
    coords = await geocode_location(loc)
    if coords is None:
        return None
    await db.users.update_one(
        {"uid": uid}, {"$set": {"lat": coords[0], "lng": coords[1]}}
    )
    return coords


@router.get("/api/discovery", response_model=DiscoveryPage)
async def discovery(
    before: Optional[str] = None,
    limit: int = DISCOVERY_PAGE_SIZE,
    radius_miles: Optional[float] = None,
    interested_in: Optional[str] = None,
    current=Depends(get_current_user),
):
    """Cursor-paginated list of candidate players.

    - `before`: created_at ISO of the last player from the previous page.
    - `limit`: page size (1..50).
    - `radius_miles`: if set, restrict to players whose geocoded location is
      within this radius of the caller. Players without coordinates are
      excluded when the filter is active.
    - `interested_in`: if set, only match players whose `interestedIn` field
      contains the keyword (case-insensitive substring match). Players who
      have flagged `privacy.interestedIn=true` are excluded.
    """
    limit = max(1, min(limit, 200))
    db = get_db()
    me = current["uid"]

    # Everyone the caller has already interacted with should drop out of
    # discovery — otherwise the "N players to discover" count never decreases
    # after adding friends or sending requests. We gather three sources in
    # parallel-friendly individual queries (each is a small indexed lookup):
    #
    #   1. Legacy swipes (like/pass from the old swipe UI, kept for back-compat)
    #   2. Friend requests I've sent AND requests sent to me
    #   3. Anyone who's already a match/friend of mine (either direction)
    exclude: set[str] = {me}

    async for d in db.swipes.find({"from_uid": me}, {"to_uid": 1, "_id": 0}).limit(1000):
        exclude.add(d["to_uid"])

    async for r in db.friend_requests.find(
        {"$or": [{"from_uid": me}, {"to_uid": me}]},
        {"from_uid": 1, "to_uid": 1, "_id": 0},
    ).limit(1000):
        exclude.add(r["from_uid"] if r["from_uid"] != me else r["to_uid"])

    async for m in db.matches.find(
        {"$or": [{"user_a": me}, {"user_b": me}]},
        {"user_a": 1, "user_b": 1, "_id": 0},
    ).limit(1000):
        exclude.add(m["user_b"] if m["user_a"] == me else m["user_a"])

    query: dict = {
        "uid": {"$nin": list(exclude)},
        # Hide demo/seed accounts forever — real users only across the app.
        "is_seed": {"$ne": True},
        # Hide profiles that haven't completed onboarding yet (no name set).
        # Without this, abandoned signups appear as empty "placeholder" cards.
        "name": {"$nin": [None, ""]},
    }
    if before:
        query["created_at"] = {"$lt": before}

    kw = (interested_in or "").strip()
    if kw:
        # Case-insensitive substring match. Escape regex metacharacters so
        # a user typing "tournaments (doubles)" doesn't blow up the engine.
        pattern = re.escape(kw)
        query["interestedIn"] = {"$regex": pattern, "$options": "i"}
        # Hide players who explicitly marked the field private.
        query["$or"] = [
            {"privacy.interestedIn": {"$ne": True}},
            {"privacy.interestedIn": {"$exists": False}},
        ]

    viewer_coords: Optional[tuple[float, float]] = None
    if radius_miles is not None and radius_miles > 0:
        viewer_coords = await _viewer_coords(current["uid"])
        # Only candidates with stored coords can pass a distance filter.
        query["lat"] = {"$ne": None}
        query["lng"] = {"$ne": None}

    # When a radius filter is active we scan a wider pool because most rows
    # will be filtered out client-side after the haversine check. Cap the
    # scan at 800 rows so we don't full-table-scan in edge cases.
    scan_limit = limit
    if viewer_coords is not None:
        scan_limit = min(limit * RADIUS_SCAN_MULTIPLIER, 800)

    docs: list[dict] = []
    cursor = db.users.find(query).sort("created_at", -1).limit(scan_limit)
    async for doc in cursor:
        if viewer_coords is not None:
            try:
                dist = haversine_miles(
                    viewer_coords[0], viewer_coords[1],
                    float(doc["lat"]), float(doc["lng"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if dist > radius_miles:
                continue
            doc["_distance_miles"] = round(dist, 1)
        docs.append(doc)
        if len(docs) >= limit:
            break

    # Batch-fetch latest public post per user (1 query instead of N).
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
        out.append(
            DiscoveryProfile(
                **base.model_dump(),
                recent_post=recent,
                distance_miles=doc.get("_distance_miles"),
            )
        )

    next_cursor = docs[-1].get("created_at") if len(docs) == limit and docs else None
    return DiscoveryPage(players=out, next_cursor=next_cursor)
