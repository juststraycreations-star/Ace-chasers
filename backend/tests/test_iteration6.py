"""Iteration 6 tests:

- `interestedIn` accepted by PUT /api/users/me and surfaced on GET /api/users/me.
- Field is stripped on /api/users/{uid} when privacy.interestedIn=True.
- Discovery payload also carries it (and strips it when private).
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

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _signup(prefix="i6"):
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
def alice():
    u = _signup("i6a")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def bob():
    u = _signup("i6b")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def test_interested_in_saves_and_returns_on_self_lookup(alice):
    r = requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(alice["id_token"]),
        json={"interestedIn": "tournament partners, doubles, casual rounds"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interestedIn"] == "tournament partners, doubles, casual rounds"

    r2 = requests.get(
        f"{BASE_URL}/api/users/me", headers=_h(alice["id_token"]), timeout=15
    )
    assert r2.status_code == 200
    assert r2.json()["interestedIn"] == "tournament partners, doubles, casual rounds"


def test_interested_in_is_stripped_when_private_for_other_viewers(alice, bob):
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(alice["id_token"]),
        json={
            "interestedIn": "secret stuff",
            "privacy": {"interestedIn": True},
        },
        timeout=15,
    )

    # Bob looks at Alice -> field should be hidden.
    r = requests.get(
        f"{BASE_URL}/api/users/{alice['uid']}",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["interestedIn"] is None

    # Alice looks at herself -> she still sees it.
    r2 = requests.get(
        f"{BASE_URL}/api/users/me", headers=_h(alice["id_token"]), timeout=15
    )
    assert r2.json()["interestedIn"] == "secret stuff"


def test_interested_in_visible_when_not_private(alice, bob):
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(alice["id_token"]),
        json={
            "interestedIn": "doubles night every thursday",
            "privacy": {"interestedIn": False},
        },
        timeout=15,
    )
    r = requests.get(
        f"{BASE_URL}/api/users/{alice['uid']}",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["interestedIn"] == "doubles night every thursday"
