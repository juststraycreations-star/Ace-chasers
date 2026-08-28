"""Iteration 12 tests: Discovery only surfaces users who have completed
onboarding (a name set). The previous iteration filtered is_seed=True but
the real "placeholder cards" on production were abandoned signups with no
name — those should be hidden too."""
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

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _signup(prefix="i12"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
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
def viewer():
    u = _signup("i12v")
    _sync(u)
    # Give the viewer a name so they don't filter themselves out (Discovery
    # already excludes the caller, but it's the realistic state).
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"name": "Viewer i12"},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture
def nameless_user():
    """Sign up a user and DO NOT set a name. They should never appear in
    other people's Discovery feed."""
    u = _signup("i12nameless")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture
def named_user():
    u = _signup("i12named")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"name": "Named i12"},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def test_discovery_hides_users_without_a_name(viewer, nameless_user, named_user):
    r = requests.get(
        f"{BASE_URL}/api/discovery", headers=_h(viewer["id_token"]), timeout=15
    )
    assert r.status_code == 200
    uids = [p["uid"] for p in r.json()["players"]]
    assert nameless_user["uid"] not in uids, (
        "Users without a name MUST be excluded from Discovery"
    )
    assert named_user["uid"] in uids, "Users with a name MUST appear in Discovery"


def test_discovery_hides_users_whose_name_is_empty_string(viewer):
    """Explicit empty-string names ('' instead of missing/null) also hidden."""
    u = _signup("i12empty")
    _sync(u)
    # Reach in via Mongo to set name="" since the API model rejects empty.
    from db import get_db

    async def set_empty():
        db = get_db()
        await db.users.update_one({"uid": u["uid"]}, {"$set": {"name": ""}})

    asyncio.get_event_loop().run_until_complete(set_empty())
    try:
        r = requests.get(
            f"{BASE_URL}/api/discovery", headers=_h(viewer["id_token"]), timeout=15
        )
        assert r.status_code == 200
        uids = [p["uid"] for p in r.json()["players"]]
        assert u["uid"] not in uids
    finally:
        try:
            requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
        except Exception:
            pass
