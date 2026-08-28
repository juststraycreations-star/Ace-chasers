"""Iteration 65 — Regenerate round join code.

Verifies `PUT /api/rounds/{id}/regenerate-code`:
  1) Director gets a fresh 4-char code that follows the same alphabet
     rules as create-time generation and differs from the previous one.
  2) Non-director callers get 403.
  3) Completed rounds return 409 (no security value in rotating a code
     on a done round + would recycle codes into the active pool).
  4) After rotation the old code no longer resolves; the new one does.
"""
from __future__ import annotations
import os
import re
import uuid
import time
import asyncio
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "")
            .rstrip("/") or "http://localhost:8001")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
ALLOWED = re.compile(r"^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4,5}$")


def _h(t): return {"Authorization": f"Bearer {t}"}
def _run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i65_{uuid.uuid4().hex[:10]}@example.com"
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
        "name": f"Rotate {uuid.uuid4().hex[:6]}",
        "format": "Singles", "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _new_round(director, league_id):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
                            headers=_h(director["token"]), timeout=15).json()
    payload = {
        "name": "W1", "date": "2026-02-16", "holes": 3,
        "par_per_hole": [3, 3, 3], "course_location": "Test",
    }
    if seasons: payload["season_id"] = seasons[0]["id"]
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/rounds",
        json=payload, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


async def _set_round_status(round_id, status):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.rounds.update_one({"id": round_id}, {"$set": {"status": status}})
    client.close()


def test_director_can_rotate_and_gets_a_fresh_code():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    old_code = rd["join_code"]
    assert old_code

    r = requests.put(f"{BASE_URL}/api/rounds/{rd['id']}/regenerate-code",
                     headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    new_code = body["join_code"]
    assert new_code != old_code
    assert body["old_code"] == old_code
    assert ALLOWED.match(new_code), f"regenerated code {new_code!r} has bad chars"
    for bad in ("O", "0", "I", "1"):
        assert bad not in new_code


def test_non_director_gets_403():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    attacker = _signup()
    # Attacker joins the league but doesn't become director.
    jr = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join", json={},
                       headers=_h(attacker["token"]), timeout=15)
    assert jr.status_code == 200
    r = requests.put(f"{BASE_URL}/api/rounds/{rd['id']}/regenerate-code",
                     headers=_h(attacker["token"]), timeout=15)
    assert r.status_code == 403


def test_completed_round_rotation_returns_409():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    _run(_set_round_status(rd["id"], "completed"))
    r = requests.put(f"{BASE_URL}/api/rounds/{rd['id']}/regenerate-code",
                     headers=_h(director["token"]), timeout=15)
    assert r.status_code == 409


def test_old_code_stops_resolving_after_rotation():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    old_code = rd["join_code"]

    r = requests.put(f"{BASE_URL}/api/rounds/{rd['id']}/regenerate-code",
                     headers=_h(director["token"]), timeout=15).json()
    new_code = r["join_code"]

    # Old code is dead.
    dead = requests.get(f"{BASE_URL}/api/rounds/join/{old_code}",
                        headers=_h(director["token"]), timeout=15)
    assert dead.status_code == 404
    # New code resolves.
    alive = requests.get(f"{BASE_URL}/api/rounds/join/{new_code}",
                          headers=_h(director["token"]), timeout=15)
    assert alive.status_code == 200
    assert alive.json()["round"]["id"] == rd["id"]


def test_regenerate_missing_round_returns_404():
    director = _signup()
    r = requests.put(f"{BASE_URL}/api/rounds/does-not-exist-{uuid.uuid4().hex}/regenerate-code",
                     headers=_h(director["token"]), timeout=15)
    assert r.status_code == 404
