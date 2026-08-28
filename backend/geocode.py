"""Lightweight geocoding helpers.

Uses the public Nominatim (OpenStreetMap) endpoint — no API key required.
We respect their usage policy: 1 req/sec, descriptive User-Agent, and we
cache results in Mongo `geocode_cache` so we never re-geocode the same
free-text location twice.

A user's `location` field is free text like "Portland, OR" or "Seattle".
On every profile save we attempt to geocode it and persist {lat, lng} on
the user doc. Discovery uses these coords + haversine to surface players
within the caller's chosen radius.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Optional

import httpx

from db import get_db

logger = logging.getLogger("geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = os.environ.get(
    "GEOCODE_USER_AGENT", "AceChasers/1.0 (https://acechasers.net)"
)
_LOCK = asyncio.Lock()  # serialize requests so we don't hammer Nominatim


async def geocode_location(text: str) -> Optional[tuple[float, float]]:
    """Resolve `text` -> (lat, lng) using Nominatim with a Mongo cache.

    Returns None for empty / unresolvable strings. Failures are swallowed
    and logged so a flaky geocoder never breaks profile saves.
    """
    text = (text or "").strip()
    if not text:
        return None
    key = text.lower()
    db = get_db()
    cached = await db.geocode_cache.find_one({"key": key})
    if cached:
        if cached.get("lat") is None or cached.get("lng") is None:
            return None
        return float(cached["lat"]), float(cached["lng"])

    async with _LOCK:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={"q": text, "format": "json", "limit": 1},
                    headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                )
                resp.raise_for_status()
                hits = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nominatim lookup failed for %r: %s", text, exc)
            return None

    coords: Optional[tuple[float, float]] = None
    if hits:
        try:
            coords = (float(hits[0]["lat"]), float(hits[0]["lon"]))
        except (KeyError, TypeError, ValueError):
            coords = None

    await db.geocode_cache.update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "lat": coords[0] if coords else None,
                "lng": coords[1] if coords else None,
            }
        },
        upsert=True,
    )
    return coords


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng pairs, in miles."""
    R_MILES = 3958.7613
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R_MILES * c
