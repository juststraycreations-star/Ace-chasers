"""Iteration 39 — Bracket auto-advance + Phase-4 completion sanity.

Deliberately uses only TWO Firebase signups (to avoid the IP-level
`TOO_MANY_ATTEMPTS_TRY_LATER` we hit during prior batch runs) and one
brand-new match-play round.

Verifies:
 1) Item 1: When both scorecards on a Match-Play round are finalized,
    the bracket match auto-resolves and the winner is advanced.
 2) Item 4: `/rounds/{id}` GET, `/rounds/{id}/join`, `/rounds/{id}/status`
    still work after being moved to leagues_rounds_router.py.
"""
from __future__ import annotations
import os
import uuid
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(retries=6, backoff=15):
    for attempt in range(retries):
        email = f"TEST_i39_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        # Rate limited or transient — back off
        time.sleep(backoff)
    pytest.skip(f"Firebase Identity still rate-limiting after {retries} attempts")


def test_bracket_auto_advance_and_phase4_endpoints():
    director = _signup()
    player = _signup()

    # Create a Match Play league + join with the second player
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i39-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Match Play", "entry_fee": 0.0},
        headers=_h(director["token"]), timeout=15).json()
    j = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
        headers=_h(player["token"]), timeout=15)
    assert j.status_code == 200

    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
        headers=_h(director["token"]), timeout=15).json()
    m_ids = [m["id"] for m in members]

    # Seed a 2-player bracket (single match)
    seed = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/bracket/seed",
        json={"member_ids": m_ids}, headers=_h(director["token"]), timeout=15)
    assert seed.status_code == 200, seed.text
    bracket = seed.json()
    assert len(bracket["tiers"]) == 1  # 2 seeds → 1 tier, 1 match
    match_id = bracket["tiers"][0][0]["id"]

    # Create a round on the league (Phase 4: verifies rounds POST still works
    # since it stayed in leagues_router.py — good sanity)
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(director["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "MP-R1", "date": "2026-06-01",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(director["token"]), timeout=15).json()

    # Phase-4: /rounds/{id} GET (moved)
    got = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}",
        headers=_h(director["token"]), timeout=15)
    assert got.status_code == 200
    assert got.json()["round"]["id"] == rd["id"]

    # Phase-4: /rounds/{id}/status PATCH (moved)
    up = requests.patch(f"{BASE_URL}/api/rounds/{rd['id']}/status",
        json={"status": "active"},
        headers=_h(director["token"]), timeout=15)
    assert up.status_code == 200

    # Phase-4: /rounds/{id}/join (moved) — both players self-enroll
    j1 = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join",
        headers=_h(director["token"]), timeout=15)
    j2 = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join",
        headers=_h(player["token"]), timeout=15)
    assert j1.status_code == 200 and j2.status_code == 200
    sc1 = j1.json()["scorecard"]["id"]
    sc2 = j2.json()["scorecard"]["id"]

    # Post scores. Director scores 4s, player scores 3s → player wins.
    for hole in range(1, 10):
        requests.patch(f"{BASE_URL}/api/scorecards/{sc1}/score",
            json={"hole": hole, "strokes": 4}, headers=_h(director["token"]), timeout=15)
        requests.patch(f"{BASE_URL}/api/scorecards/{sc2}/score",
            json={"hole": hole, "strokes": 3}, headers=_h(player["token"]), timeout=15)

    # Finalize director's card first — bracket NOT yet resolvable (player's card still open)
    r1 = requests.post(f"{BASE_URL}/api/scorecards/{sc1}/finalize",
        json={"certified": True}, headers=_h(director["token"]), timeout=15)
    assert r1.status_code == 200
    assert r1.json()["bracket_advance"]["pending"] is True

    # Finalize player's card → auto-resolve
    r2 = requests.post(f"{BASE_URL}/api/scorecards/{sc2}/finalize",
        json={"certified": True}, headers=_h(player["token"]), timeout=15)
    assert r2.status_code == 200, r2.text
    resolved = r2.json()["bracket_advance"]
    assert resolved.get("resolved") is True, resolved
    # Player had 27 (3*9), director had 36 → player wins
    winner_expected = j2.json()["scorecard"]["member_id"]
    assert resolved["winner_id"] == winner_expected

    # Verify bracket state persisted
    b = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/bracket",
        headers=_h(director["token"]), timeout=15).json()
    match = b["tiers"][0][0]
    assert match["winner_id"] == winner_expected
    assert match["a_score"] is not None and match["b_score"] is not None
