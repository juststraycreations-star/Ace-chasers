"""Iteration 16: profile-level Ace Club (aceClub + aceClubCount)."""
from __future__ import annotations

import os
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


def _signup(prefix="i16"):
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


@pytest.fixture
def viewer():
    u = _signup("i16v")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"name": "Viewer i16"},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture
def ace_player():
    u = _signup("i16ace")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"name": "Ace Player", "aceClub": True, "aceClubCount": 12},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def test_ace_club_persists_on_self_lookup(ace_player):
    r = requests.get(
        f"{BASE_URL}/api/users/me",
        headers=_h(ace_player["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["aceClub"] is True
    assert body["aceClubCount"] == 12


def test_ace_club_visible_on_other_viewers_lookup(viewer, ace_player):
    r = requests.get(
        f"{BASE_URL}/api/users/{ace_player['uid']}",
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["aceClub"] is True
    assert body["aceClubCount"] == 12


def test_ace_club_appears_on_discovery_card(viewer, ace_player):
    r = requests.get(
        f"{BASE_URL}/api/discovery",
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    target = next((p for p in r.json()["players"] if p["uid"] == ace_player["uid"]), None)
    assert target is not None, "ace_player should be in Discovery"
    assert target["aceClub"] is True
    assert target["aceClubCount"] == 12


def test_toggle_off_clears_count(ace_player):
    # Disable ace club; count should be allowed null or zeroed.
    r = requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(ace_player["id_token"]),
        json={"aceClub": False, "aceClubCount": None},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aceClub"] is False
    assert body["aceClubCount"] is None
