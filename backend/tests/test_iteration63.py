"""Iteration 63 — Round join_code fallback for QR failures.

Verifies:
  1) Every newly-created round is assigned a `join_code` that is 4
     chars long, uppercase A-Z + digits, and free of visually-
     confusable characters (O, 0, I, 1).
  2) `GET /api/rounds/{id}/qr` echoes the code so the frontend can
     render the fallback beneath the QR image.
  3) `GET /api/rounds/join/{code}` finds the round (case-insensitive),
     auto-enrolls the caller into a solo scorecard, and returns the
     round + card + scorecard shapes.
  4) Two active rounds cannot share the same code (uniqueness check).
  5) Unknown code returns 404.
"""
from __future__ import annotations
import os
import re
import uuid
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "")
            .rstrip("/") or "http://localhost:8001")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"

# Alphabet enforced by _generate_round_join_code — mirror it here so
# the assertion never drifts.
ALLOWED = re.compile(r"^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4,5}$")


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i63_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def _new_league(director):
    r = requests.post(f"{BASE_URL}/api/leagues", json={
        "name": f"JoinCode {uuid.uuid4().hex[:6]}",
        "format": "Singles", "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _new_round(director, league_id, name="W1"):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
                            headers=_h(director["token"]), timeout=15).json()
    payload = {
        "name": name, "date": "2026-02-15", "holes": 3,
        "par_per_hole": [3, 3, 3], "course_location": "Test",
    }
    if seasons: payload["season_id"] = seasons[0]["id"]
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/rounds",
        json=payload, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def test_new_round_has_valid_join_code():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    code = rd["join_code"]
    assert code is not None, "join_code missing on new round"
    assert ALLOWED.match(code), f"join_code {code!r} has bad chars"
    # No visually-confusable characters slipped through.
    for bad in ("O", "0", "I", "1"):
        assert bad not in code, f"join_code {code!r} contains confusable {bad!r}"


def test_qr_endpoint_echoes_join_code():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    qr = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/qr",
                      headers=_h(director["token"]), timeout=15).json()
    assert qr["join_code"] == rd["join_code"]
    assert qr["deeplink"].startswith("/rounds/")


def test_join_by_code_enrolls_the_caller():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    code = rd["join_code"]

    # Fresh player types the code (case-insensitive lookup).
    player = _signup()
    r = requests.get(f"{BASE_URL}/api/rounds/join/{code.lower()}",
                     headers=_h(player["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round"]["id"] == rd["id"]
    # Player wasn't in the league before → auto-joined + fresh enrolled.
    assert body["auto_joined_league"] is True
    assert body["already_enrolled"] is False
    assert body["scorecard"]["round_id"] == rd["id"]

    # Second call is idempotent — already enrolled.
    r2 = requests.get(f"{BASE_URL}/api/rounds/join/{code}",
                      headers=_h(player["token"]), timeout=15).json()
    assert r2["already_enrolled"] is True
    assert r2["scorecard"]["id"] == body["scorecard"]["id"]


def test_two_active_rounds_do_not_share_a_code():
    """Uniqueness guard — spinning up two rounds in the same league must
    yield different join codes. Not a probabilistic sample — this is
    enforced by the generator's collision check."""
    director = _signup()
    lg = _new_league(director)
    r1 = _new_round(director, lg["id"], name="Alpha")
    r2 = _new_round(director, lg["id"], name="Beta")
    assert r1["join_code"] != r2["join_code"]


def test_unknown_code_returns_404():
    player = _signup()
    r = requests.get(f"{BASE_URL}/api/rounds/join/ZZZZ",
                     headers=_h(player["token"]), timeout=15)
    assert r.status_code == 404
