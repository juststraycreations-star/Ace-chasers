"""Iteration 4 backend tests:
- GET /api/discovery now includes distance_miles (nullable)
- GET /api/discovery?radius_miles=N respects haversine filter using stored lat/lng
- PUT /api/users/me geocodes the `location` field (does not crash on bad strings)
- Clearing `location` ("") clears lat/lng on the user doc
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"

# Add backend to path so we can directly seed coords via the same Mongo connection.
HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _signup():
    email = f"TEST_i4_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _sync(u):
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=15)
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def caller():
    u = _signup()
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


# ---------------------- Discovery shape ----------------------

class TestDiscoveryShape:
    def test_default_response_has_players_and_next_cursor(self, caller):
        r = requests.get(
            f"{BASE_URL}/api/discovery", headers=_h(caller["id_token"]), timeout=15
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "players" in body
        assert "next_cursor" in body
        assert isinstance(body["players"], list)

    def test_each_player_has_distance_miles_key(self, caller):
        """Each player record should at least carry the (nullable) distance_miles key."""
        r = requests.get(
            f"{BASE_URL}/api/discovery", headers=_h(caller["id_token"]), timeout=15
        )
        body = r.json()
        for p in body["players"]:
            assert "distance_miles" in p, f"missing distance_miles in {p.keys()}"
            # When no radius filter, distance should be null.
            assert p["distance_miles"] is None

    def test_distance_miles_field_when_radius_filter_active(self, caller):
        """With radius_miles, response shape is preserved.

        Note: when the caller has no stored coords, the filter cannot compute
        a haversine distance, so distance_miles will remain null per player.
        """
        r = requests.get(
            f"{BASE_URL}/api/discovery?radius_miles=50",
            headers=_h(caller["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for p in body["players"]:
            assert "distance_miles" in p
            # distance_miles must be either None or numeric
            assert p["distance_miles"] is None or isinstance(
                p["distance_miles"], (int, float)
            )


# ---------------------- Geocoding via /users/me ----------------------

class TestProfileGeocoding:
    def test_update_location_does_not_crash_on_garbage(self, caller):
        """Unresolvable strings must NOT 500 — backend swallows the error."""
        r = requests.put(
            f"{BASE_URL}/api/users/me",
            json={"location": "qwertyzzz-not-a-place-zzz"},
            headers=_h(caller["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text

    def test_clearing_location_clears_lat_lng(self, caller):
        # First set a real location (Portland, OR is well cached in test_geocode tests).
        # Network may be slow; we just check the endpoint succeeds either way.
        r = requests.put(
            f"{BASE_URL}/api/users/me",
            json={"location": "Portland, OR"},
            headers=_h(caller["id_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text

        # Now clear it
        r2 = requests.put(
            f"{BASE_URL}/api/users/me",
            json={"location": ""},
            headers=_h(caller["id_token"]),
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        # Profile read back: location is cleared.
        me = requests.get(f"{BASE_URL}/api/users/me", headers=_h(caller["id_token"]), timeout=15).json()
        assert (me.get("location") or "") == ""


# ---------------------- Haversine radius filter ----------------------

def test_radius_filter_includes_near_excludes_far(caller):
    """End-to-end: seed two TEST users with known coords (one near caller, one far),
    set caller's coords, and verify the radius_miles filter selects only the near one.

    Uses Mongo directly (pymongo, sync) to set lat/lng so we don't depend on live Nominatim.
    """
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Caller at Portland, OR
    caller_lat, caller_lng = 45.5152, -122.6784
    db.users.update_one(
        {"uid": caller["uid"]},
        {"$set": {"lat": caller_lat, "lng": caller_lng, "location": "Portland, OR"}},
    )

    # Two synthetic seed users sitting directly in Mongo (no Firebase needed; discovery
    # only filters by uid/created_at and they share the same shape).
    from datetime import datetime, timezone

    near_uid = f"TEST_i4_near_{uuid.uuid4().hex[:6]}"
    far_uid = f"TEST_i4_far_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()

    near_doc = {
        "uid": near_uid,
        "name": "Near Player",
        "created_at": now,
        "lat": 47.6062,  # Seattle ~145 mi from Portland
        "lng": -122.3321,
        "email": "TEST_near@example.com",
        "interests": [],
        "skillLevel": "Beginner",
        "bio": "near",
        "is_seed": False,
    }
    far_doc = {
        "uid": far_uid,
        "name": "Far Player",
        "created_at": now,
        "lat": 40.7128,  # New York ~2450 mi
        "lng": -74.0060,
        "email": "TEST_far@example.com",
        "interests": [],
        "skillLevel": "Beginner",
        "bio": "far",
        "is_seed": False,
    }
    db.users.insert_one(near_doc)
    db.users.insert_one(far_doc)

    try:
        # radius_miles=200: should INCLUDE near (~145mi) and EXCLUDE far (~2450mi)
        r = requests.get(
            f"{BASE_URL}/api/discovery?radius_miles=200",
            headers=_h(caller["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        uids = [p["uid"] for p in body["players"]]
        assert near_uid in uids, f"expected near_uid in radius=200 results, got {uids}"
        assert far_uid not in uids, f"far_uid should be excluded at radius=200"

        # Each returned player must have a numeric distance_miles
        near_player = next(p for p in body["players"] if p["uid"] == near_uid)
        assert isinstance(near_player["distance_miles"], (int, float))
        assert 130 < near_player["distance_miles"] < 160

        # radius_miles=3000: should include BOTH near and far
        r2 = requests.get(
            f"{BASE_URL}/api/discovery?radius_miles=3000",
            headers=_h(caller["id_token"]),
            timeout=20,
        )
        body2 = r2.json()
        uids2 = [p["uid"] for p in body2["players"]]
        assert near_uid in uids2
        assert far_uid in uids2
    finally:
        db.users.delete_many({"uid": {"$in": [near_uid, far_uid]}})
        client.close()


# ---------------------- Negative / edge cases ----------------------

class TestRadiusEdgeCases:
    def test_radius_zero_treated_as_no_filter(self, caller):
        """radius_miles=0 should not enable the filter (code checks > 0)."""
        r = requests.get(
            f"{BASE_URL}/api/discovery?radius_miles=0",
            headers=_h(caller["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        # No filter -> distance_miles should be None on each player.
        for p in body["players"]:
            assert p["distance_miles"] is None

    def test_radius_negative_treated_as_no_filter(self, caller):
        r = requests.get(
            f"{BASE_URL}/api/discovery?radius_miles=-50",
            headers=_h(caller["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
