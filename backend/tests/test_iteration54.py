"""Iteration 54 — Division-scoped Leaderboard rows.

Verifies that `GET /api/rounds/{id}/leaderboard` returns a `division`
string on every singles-mode row so the frontend can group members and
render one Share Card PNG per division.

To keep this cheap on Firebase Identity, we only need one signup — the
director is auto-added as a member with division defaulting to "Open".
We then flip the member's division via direct Mongo write and confirm
the leaderboard response reflects it.
"""
from __future__ import annotations
import os
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


def _h(t): return {"Authorization": f"Bearer {t}"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i54_{uuid.uuid4().hex[:10]}@example.com"
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
        "name": f"Div Cards {uuid.uuid4().hex[:6]}",
        "format": "Singles",
        "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _new_round(director, league_id):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
                            headers=_h(director["token"]), timeout=15).json()
    season_id = seasons[0]["id"] if seasons else None
    payload = {
        "name": "Week 1",
        "date": "2026-02-14",
        "holes": 3,
        "par_per_hole": [3, 3, 3],
        "course_location": "Test Course",
    }
    if season_id:
        payload["season_id"] = season_id
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/rounds",
        json=payload, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _join_round(director, round_id):
    r = requests.post(f"{BASE_URL}/api/rounds/{round_id}/join",
        json={}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["scorecard"]


def _score(director, sc_id, hole, strokes):
    r = requests.patch(f"{BASE_URL}/api/scorecards/{sc_id}/score",
        json={"hole": hole, "strokes": strokes},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text


def test_leaderboard_row_carries_division_default_open():
    """A round with only the director (default division "Open") must
    return a leaderboard row that carries `division: "Open"`."""
    director = _signup()
    lg = _new_league(director)
    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
                            headers=_h(director["token"]), timeout=15).json()
    assert len(members) == 1
    dir_member = members[0]
    rd = _new_round(director, lg["id"])
    sc = _join_round(director, rd["id"])
    _score(director, sc["id"], 1, 3)

    lb = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/leaderboard",
                       headers=_h(director["token"]), timeout=15).json()
    assert lb["mode"] == "singles"
    assert len(lb["rows"]) == 1
    row = lb["rows"][0]
    assert "division" in row
    assert row["division"] == "Open"


def test_leaderboard_row_reflects_custom_division():
    """After flipping the director's member.division via direct Mongo,
    the leaderboard row must echo the new label — this is exactly what
    the frontend groups on to render one Share Card PNG per division."""
    director = _signup()
    lg = _new_league(director)
    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
                            headers=_h(director["token"]), timeout=15).json()
    dir_member = members[0]

    async def _flip():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.league_members.update_one(
            {"id": dir_member["id"]},
            {"$set": {"division": "MPO"}},
        )
        client.close()
    _run(_flip())

    rd = _new_round(director, lg["id"])
    sc = _join_round(director, rd["id"])
    _score(director, sc["id"], 1, 3)

    lb = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/leaderboard",
                       headers=_h(director["token"]), timeout=15).json()
    assert lb["rows"][0]["division"] == "MPO"
