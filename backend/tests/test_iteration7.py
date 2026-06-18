"""Iteration 7 tests:

- /api/discovery?interested_in=keyword does case-insensitive substring
  matching on the candidate's interestedIn field.
- Players who marked interestedIn private are excluded when the filter is on.
- POST /api/messages/{uid} round-trip + GET /api/messages/threads sees it.
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


def _signup(prefix="i7"):
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
    u = _signup("i7v")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def doubles_player():
    u = _signup("i7dbl")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"interestedIn": "doubles night every thursday"},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def private_player():
    u = _signup("i7priv")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={
            "interestedIn": "doubles secret",
            "privacy": {"interestedIn": True},
        },
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def test_discovery_filter_finds_matching_player(viewer, doubles_player):
    r = requests.get(
        f"{BASE_URL}/api/discovery",
        params={"interested_in": "doubles"},
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    uids = [p["uid"] for p in r.json()["players"]]
    assert doubles_player["uid"] in uids


def test_discovery_filter_excludes_private_player(viewer, private_player):
    r = requests.get(
        f"{BASE_URL}/api/discovery",
        params={"interested_in": "doubles"},
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    uids = [p["uid"] for p in r.json()["players"]]
    assert private_player["uid"] not in uids


def test_discovery_filter_is_case_insensitive(viewer, doubles_player):
    r = requests.get(
        f"{BASE_URL}/api/discovery",
        params={"interested_in": "DOUBLES"},
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    uids = [p["uid"] for p in r.json()["players"]]
    assert doubles_player["uid"] in uids


def test_send_message_round_trip(viewer, doubles_player):
    # Viewer sends a message to doubles_player.
    body = f"hello from iter7 {uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/messages/{doubles_player['uid']}",
        headers=_h(viewer["id_token"]),
        json={"body": body},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    msg = r.json()
    assert msg["body"] == body
    assert msg["is_mine"] is True

    # Threads endpoint now lists the new conversation.
    tr = requests.get(
        f"{BASE_URL}/api/messages/threads",
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert tr.status_code == 200
    threads = tr.json()
    other_uids = [t["with_user"]["uid"] for t in threads]
    assert doubles_player["uid"] in other_uids
    # Receiver sees it as unread.
    rr = requests.get(
        f"{BASE_URL}/api/messages/threads",
        headers=_h(doubles_player["id_token"]),
        timeout=15,
    )
    receiver_threads = rr.json()
    me_row = next(
        (t for t in receiver_threads if t["with_user"]["uid"] == viewer["uid"]), None
    )
    assert me_row is not None
    assert me_row["unread"] >= 1


def test_cannot_message_self(viewer):
    r = requests.post(
        f"{BASE_URL}/api/messages/{viewer['uid']}",
        headers=_h(viewer["id_token"]),
        json={"body": "talking to myself"},
        timeout=15,
    )
    assert r.status_code == 400
