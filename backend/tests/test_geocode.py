"""Tests for geocoding helper + /api/discovery radius_miles filter.

We patch out the Nominatim HTTP call so tests don't depend on the network.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def _run(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def test_haversine_miles_basic():
    from geocode import haversine_miles

    # Portland, OR (45.5152, -122.6784) -> Seattle, WA (47.6062, -122.3321)
    d = haversine_miles(45.5152, -122.6784, 47.6062, -122.3321)
    # Ground truth ~145 miles. Allow ±5mi tolerance.
    assert 140 < d < 150


def test_geocode_returns_cached_value():
    from geocode import geocode_location

    fake_db = type("FakeDB", (), {})()
    fake_db.geocode_cache = type("Coll", (), {})()
    fake_db.geocode_cache.find_one = AsyncMock(
        return_value={"key": "portland, or", "lat": 45.5152, "lng": -122.6784}
    )
    fake_db.geocode_cache.update_one = AsyncMock()

    with patch("geocode.get_db", return_value=fake_db):
        coords = _run(geocode_location("Portland, OR"))
    assert coords is not None
    assert coords == pytest.approx((45.5152, -122.6784), abs=0.001)


def test_geocode_skips_empty_input():
    from geocode import geocode_location

    assert _run(geocode_location("")) is None
    assert _run(geocode_location("   ")) is None


def test_geocode_calls_nominatim_on_miss(monkeypatch):
    import httpx
    from geocode import geocode_location

    fake_db = type("FakeDB", (), {})()
    fake_db.geocode_cache = type("Coll", (), {})()
    fake_db.geocode_cache.find_one = AsyncMock(return_value=None)
    fake_db.geocode_cache.update_one = AsyncMock()

    class _Resp:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"lat": "47.6062", "lon": "-122.3321"}]

    class _Client:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *_, **__):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with patch("geocode.get_db", return_value=fake_db):
        coords = _run(geocode_location("Seattle, WA"))
    assert coords == (47.6062, -122.3321)
    fake_db.geocode_cache.update_one.assert_awaited_once()
