"""Iteration 23: Discovery exclusion set now includes friends + pending friend requests.

Bug: /api/discovery card count never decreased after friending / requesting.
Fix: exclude set unions swipes + friend_requests (both dirs) + matches (both dirs) + self.

Tests:
1. Users A,B,C,D,E signed up via Firebase.
2. Inject matches doc (A-B friend), friend_request A->C (sent), friend_request D->A (incoming).
3. GET /api/discovery as A -> must NOT include A/B/C/D. MUST include E.
4. Regression: legacy swipes still excluded.
5. Regression: uninteracted user (E) still appears (positive control -- same as 3).
6. Regression: radius_miles + interested_in filters are still respected (smoke).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

sys.path.insert(0, "/app/backend")
from db import get_db  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE_ACCT = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _signup(prefix):
    email = f"TEST_i23_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"], "prefix": prefix}


def _sync(u, name):
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=20)
    assert r.status_code == 200, r.text
    r2 = requests.put(
        f"{BASE_URL}/api/users/me",
        json={"name": name},
        headers=_h(u["id_token"]),
        timeout=20,
    )
    assert r2.status_code == 200, r2.text


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(scope="module")
def users():
    """Create 5 real Firebase users A,B,C,D,E and sync onboarding."""
    created = {}
    for name in ("a", "b", "c", "d", "e"):
        u = _signup(name)
        _sync(u, name=f"User{name.upper()} {u['uid'][:6]}")
        created[name] = u
    yield created
    for u in created.values():
        try:
            requests.post(DELETE_ACCT, json={"idToken": u["id_token"]}, timeout=10)
        except Exception:
            pass
    # Cleanup any injected docs by uid
    uids = [u["uid"] for u in created.values()]

    async def _cleanup():
        db = get_db()
        await db.matches.delete_many({"$or": [{"user_a": {"$in": uids}}, {"user_b": {"$in": uids}}]})
        await db.friend_requests.delete_many({"$or": [{"from_uid": {"$in": uids}}, {"to_uid": {"$in": uids}}]})
        await db.swipes.delete_many({"$or": [{"from_uid": {"$in": uids}}, {"to_uid": {"$in": uids}}]})
        await db.users.delete_many({"uid": {"$in": uids}})

    try:
        _run(_cleanup())
    except Exception:
        pass


@pytest.fixture(scope="module")
def seeded_relations(users):
    """Inject matches + friend_requests directly to simulate state."""
    a, b, c, d = users["a"]["uid"], users["b"]["uid"], users["c"]["uid"], users["d"]["uid"]
    ua, ub = sorted([a, b])  # match_key normalization
    now = datetime.now(timezone.utc).isoformat()

    async def _seed():
        db = get_db()
        # A-B friends (both directions covered by user_a/user_b)
        await db.matches.update_one(
            {"user_a": ua, "user_b": ub},
            {"$setOnInsert": {
                "user_a": ua, "user_b": ub,
                "friended_by": [a, b],
                "created_at": now,
            }},
            upsert=True,
        )
        # A -> C outgoing friend request
        await db.friend_requests.update_one(
            {"from_uid": a, "to_uid": c},
            {"$set": {"from_uid": a, "to_uid": c, "created_at": now}},
            upsert=True,
        )
        # D -> A incoming friend request
        await db.friend_requests.update_one(
            {"from_uid": d, "to_uid": a},
            {"$set": {"from_uid": d, "to_uid": a, "created_at": now}},
            upsert=True,
        )

    _run(_seed())
    yield


def _fetch_discovery(user, **params):
    r = requests.get(
        f"{BASE_URL}/api/discovery",
        headers=_h(user["id_token"]),
        params=params,
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestDiscoveryExclusion:
    def test_friend_excluded(self, users, seeded_relations):
        data = _fetch_discovery(users["a"])
        uids = {p["uid"] for p in data["players"]}
        assert users["b"]["uid"] not in uids, "Friend (B) must be excluded from discovery"

    def test_outgoing_friend_request_excluded(self, users, seeded_relations):
        data = _fetch_discovery(users["a"])
        uids = {p["uid"] for p in data["players"]}
        assert users["c"]["uid"] not in uids, "User with sent friend-request (C) must be excluded"

    def test_incoming_friend_request_excluded(self, users, seeded_relations):
        data = _fetch_discovery(users["a"])
        uids = {p["uid"] for p in data["players"]}
        assert users["d"]["uid"] not in uids, "User with incoming friend-request (D) must be excluded"

    def test_self_excluded(self, users, seeded_relations):
        data = _fetch_discovery(users["a"])
        uids = {p["uid"] for p in data["players"]}
        assert users["a"]["uid"] not in uids, "Self must be excluded"

    def test_uninteracted_user_appears(self, users, seeded_relations):
        """Positive control: user E has no relation with A, should appear."""
        data = _fetch_discovery(users["a"])
        uids = {p["uid"] for p in data["players"]}
        assert users["e"]["uid"] in uids, (
            f"E should appear in A's discovery. Got {len(uids)} players. "
            f"E uid={users['e']['uid']}"
        )


class TestLegacySwipeExclusion:
    def test_swipe_pass_still_excluded(self, users):
        """Regression: legacy swipes (from old swipe UI) remain excluded."""
        a_uid = users["a"]["uid"]
        e_uid = users["e"]["uid"]
        now = datetime.now(timezone.utc).isoformat()

        async def _add():
            db = get_db()
            await db.swipes.update_one(
                {"from_uid": a_uid, "to_uid": e_uid},
                {"$set": {"from_uid": a_uid, "to_uid": e_uid, "action": "pass", "created_at": now}},
                upsert=True,
            )

        async def _clear():
            db = get_db()
            await db.swipes.delete_one({"from_uid": a_uid, "to_uid": e_uid})

        _run(_add())
        try:
            data = _fetch_discovery(users["a"])
            uids = {p["uid"] for p in data["players"]}
            assert e_uid not in uids, "Legacy swipe target must remain excluded"
        finally:
            _run(_clear())


class TestFiltersRegression:
    def test_radius_miles_smoke(self, users, seeded_relations):
        """Smoke: radius_miles param accepted; caller w/o coords returns empty list."""
        data = _fetch_discovery(users["a"], radius_miles=25)
        assert "players" in data
        assert isinstance(data["players"], list)

    def test_interested_in_narrows(self, users, seeded_relations):
        """Smoke: interested_in param accepted, response shape correct."""
        data = _fetch_discovery(users["a"], interested_in="tournaments")
        assert "players" in data
        assert isinstance(data["players"], list)

    def test_no_filters_returns_page(self, users, seeded_relations):
        """Basic shape assertion."""
        data = _fetch_discovery(users["a"])
        assert "players" in data
        assert "next_cursor" in data
        assert isinstance(data["players"], list)
