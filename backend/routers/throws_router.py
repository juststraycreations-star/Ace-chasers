"""throws_router — Distance Throw Tracker backend.

Stores individual throw measurements captured client-side via the HTML5
Geolocation API. Distance is computed on the client via the Haversine
formula and echoed back to the server so the row is self-contained;
the server re-validates the math with a Python Haversine implementation
so a rogue client can't inflate a leaderboard.
"""
from __future__ import annotations
import math
import secrets
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .leagues_router import api_router, db, get_current_user


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


EARTH_RADIUS_FEET = 20_902_231  # mean Earth radius in feet
MAX_REASONABLE_FEET = 2000       # sanity ceiling (world record ~1109 ft)


def haversine_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in feet."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(EARTH_RADIUS_FEET * c, 1)


class ThrowCreate(BaseModel):
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    disc: Optional[str] = None
    notes: Optional[str] = None
    round_id: Optional[str] = None
    hole: Optional[int] = None
    # Client-computed distance — server re-computes and stores its own value.
    client_distance_ft: Optional[float] = None


@api_router.post("/throws")
async def create_throw(payload: ThrowCreate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None),
                        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    user = await get_current_user(request, session_token, authorization)
    # Idempotent replay: if the client retried after a flaky sync, return the
    # original response instead of double-inserting the throw.
    if idempotency_key:
        cached = await db.idempotency_keys.find_one(
            {"key": idempotency_key, "scope": "throw_create", "user_id": user.user_id},
            {"_id": 0, "response": 1},
        )
        if cached and cached.get("response"):
            return cached["response"]
    for v in (payload.start_lat, payload.start_lon, payload.end_lat, payload.end_lon):
        if not -180 <= v <= 180:
            raise HTTPException(status_code=400, detail="Invalid coordinate")
    server_ft = haversine_feet(payload.start_lat, payload.start_lon,
                                 payload.end_lat, payload.end_lon)
    if server_ft > MAX_REASONABLE_FEET:
        raise HTTPException(status_code=400,
                             detail=f"Distance {server_ft}ft exceeds sanity cap {MAX_REASONABLE_FEET}ft")
    doc = {
        "id": secrets.token_hex(10),
        "user_id": user.user_id,
        "start": {"lat": payload.start_lat, "lon": payload.start_lon},
        "end": {"lat": payload.end_lat, "lon": payload.end_lon},
        "distance_ft": server_ft,
        "client_distance_ft": payload.client_distance_ft,
        "disc": payload.disc,
        "notes": payload.notes,
        "round_id": payload.round_id,
        "hole": payload.hole,
        "created_at": _now_iso(),
    }
    await db.throws.insert_one(doc)
    doc.pop("_id", None)
    if idempotency_key:
        try:
            await db.idempotency_keys.insert_one({
                "key": idempotency_key,
                "scope": "throw_create",
                "user_id": user.user_id,
                "response": doc,
                "created_at": _now_iso(),
            })
        except Exception:
            pass
    return doc


@api_router.get("/throws")
async def list_throws(request: Request,
                       limit: int = 50,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rows = await db.throws.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(min(max(limit, 1), 200)).to_list(200)
    # Personal best across all rows (feet)
    pb = max((r.get("distance_ft") or 0 for r in rows), default=0)
    return {"throws": rows, "personal_best_ft": pb, "count": len(rows)}
