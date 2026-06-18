"""Iteration 8 tests:

Frontend Profile chip toggle now appends the chip's *label* into the
`interestedIn` text field. Since the chip values stored on Discovery are
the lowercase keywords ("doubles", "tournament", ...) and the Discovery
filter does case-insensitive substring matching, these tests assert end-
to-end label→keyword parity:

  - PUT /api/users/me with interestedIn="Doubles" → /api/discovery?interested_in=doubles
    surfaces this user.
  - PUT with interestedIn="Tournaments" → filter "tournament" surfaces user.
  - Multi-label "Doubles, Putting" → filter "putt" finds user (and "doubles" too).
  - Removing the label from the saved text removes them from the filter.
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


def _signup(prefix="i8"):
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


def _put_interested(u, text, privacy=None):
    body = {"interestedIn": text}
    if privacy is not None:
        body["privacy"] = {"interestedIn": bool(privacy)}
    r = requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json=body,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _discovery_uids(viewer, keyword=None):
    params = {"interested_in": keyword} if keyword else {}
    r = requests.get(
        f"{BASE_URL}/api/discovery",
        params=params,
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return [p["uid"] for p in r.json()["players"]]


@pytest.fixture(scope="module")
def viewer():
    u = _signup("i8v")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def chip_player():
    """Player whose interestedIn is set the same way the chip UI sets it
    — i.e. the label string ('Doubles')."""
    u = _signup("i8chip")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


# Profile chip 'Doubles' (label) → Discovery filter 'doubles' (keyword) parity.
def test_chip_label_doubles_surfaces_via_discovery_filter(viewer, chip_player):
    _put_interested(chip_player, "Doubles")
    uids = _discovery_uids(viewer, "doubles")
    assert chip_player["uid"] in uids


# Tournaments label → tournament keyword (the substring match handles plural form).
def test_chip_label_tournaments_surfaces_via_tournament_filter(viewer, chip_player):
    _put_interested(chip_player, "Tournaments")
    uids = _discovery_uids(viewer, "tournament")
    assert chip_player["uid"] in uids


# Multi-chip selection: 'Doubles, Putting' should match BOTH filters.
def test_multi_chip_selection_matches_each_filter(viewer, chip_player):
    _put_interested(chip_player, "Doubles, Putting")
    assert chip_player["uid"] in _discovery_uids(viewer, "doubles")
    assert chip_player["uid"] in _discovery_uids(viewer, "putt")


# Removing the label from the text removes the user from that filter result.
def test_removing_label_drops_from_filter(viewer, chip_player):
    _put_interested(chip_player, "early-morning rounds")  # no chip keywords
    uids = _discovery_uids(viewer, "doubles")
    assert chip_player["uid"] not in uids


# Free-text 'tournament partners' still surfaces under tournament filter (regression).
def test_free_text_tournament_partners_regression(viewer, chip_player):
    _put_interested(chip_player, "tournament partners")
    uids = _discovery_uids(viewer, "tournament")
    assert chip_player["uid"] in uids


# Privacy still excludes the user even with the chip keyword present.
def test_privacy_excludes_chip_user(viewer, chip_player):
    _put_interested(chip_player, "Doubles", privacy=True)
    uids = _discovery_uids(viewer, "doubles")
    assert chip_player["uid"] not in uids
    # reset privacy for cleanliness
    _put_interested(chip_player, "Doubles", privacy=False)
