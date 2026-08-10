"""Iteration 40 — Manual Match Play Tie-Break UI + Rating-based auto-seed.

Follows the same 2-signups budget as iteration39 to sidestep Firebase's
IP-level `TOO_MANY_ATTEMPTS_TRY_LATER`.

Verifies:
 1) Auto-seed by rating: `POST /api/leagues/{id}/bracket/auto-seed`
    returns a `seed_order` sorted by rolling handicap (unrated players
    push to bottom seeds).
 2) Tie-break detection: When both scorecards on a Match-Play round
    finalize with identical totals, the `bracket_advance` response
    carries `tied: True` (auto-advance is blocked; the director must
    resolve manually).
 3) Manual override: The director calls `/bracket/matches/{id}/report`
    with a winner_id, resolving the tie. Response is idempotent.
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
    for _ in range(retries):
        email = f"TEST_i40_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_auto_seed_and_tie_break_override():
    director = _signup()
    player = _signup()

    # Match Play league + join
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i40-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Match Play", "entry_fee": 0.0},
        headers=_h(director["token"]), timeout=15).json()
    j = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
        headers=_h(player["token"]), timeout=15)
    assert j.status_code == 200

    # ────────────────────────────────────────────────────────────
    # (1) Auto-seed by rating — no rounds played yet → both unrated,
    #     endpoint still returns a valid ordered bracket.
    # ────────────────────────────────────────────────────────────
    auto = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/bracket/auto-seed",
        headers=_h(director["token"]), timeout=15)
    assert auto.status_code == 200, auto.text
    doc = auto.json()
    assert doc["seed_source"] == "auto_rating"
    assert len(doc["seed_order"]) == 2
    assert doc["seed_order"][0]["seed"] == 1
    assert len(doc["tiers"]) == 1
    assert len(doc["tiers"][0]) == 1
    match_id = doc["tiers"][0][0]["id"]

    # ────────────────────────────────────────────────────────────
    # (2) Force a tie: both players post identical scores, finalize.
    # ────────────────────────────────────────────────────────────
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(director["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "MP-Tie", "date": "2026-06-02",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(director["token"]), timeout=15).json()
    requests.patch(f"{BASE_URL}/api/rounds/{rd['id']}/status",
        json={"status": "active"}, headers=_h(director["token"]), timeout=15)
    j1 = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join",
        headers=_h(director["token"]), timeout=15).json()
    j2 = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join",
        headers=_h(player["token"]), timeout=15).json()
    sc1, sc2 = j1["scorecard"]["id"], j2["scorecard"]["id"]

    # Same total 3s across 9 holes → 27 vs 27 → TIE
    for hole in range(1, 10):
        requests.patch(f"{BASE_URL}/api/scorecards/{sc1}/score",
            json={"hole": hole, "strokes": 3}, headers=_h(director["token"]), timeout=15)
        requests.patch(f"{BASE_URL}/api/scorecards/{sc2}/score",
            json={"hole": hole, "strokes": 3}, headers=_h(player["token"]), timeout=15)

    r1 = requests.post(f"{BASE_URL}/api/scorecards/{sc1}/finalize",
        json={"certified": True}, headers=_h(director["token"]), timeout=15)
    assert r1.status_code == 200
    assert r1.json()["bracket_advance"].get("pending") is True

    r2 = requests.post(f"{BASE_URL}/api/scorecards/{sc2}/finalize",
        json={"certified": True}, headers=_h(player["token"]), timeout=15)
    assert r2.status_code == 200, r2.text
    tie = r2.json()["bracket_advance"]
    assert tie.get("tied") is True, tie
    assert tie["a_total"] == 27 and tie["b_total"] == 27
    assert tie["match_id"] == match_id
    assert tie.get("a_member_id") and tie.get("b_member_id")

    # Bracket has NOT resolved yet — no winner_id stamped
    b = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/bracket",
        headers=_h(director["token"]), timeout=15).json()
    assert b["tiers"][0][0]["winner_id"] is None

    # ────────────────────────────────────────────────────────────
    # (3) Director resolves the tie manually via the existing report
    #     endpoint — pick player as sudden-death winner.
    # ────────────────────────────────────────────────────────────
    winner_mid = tie["b_member_id"]
    rep = requests.post(f"{BASE_URL}/api/bracket/matches/{match_id}/report",
        json={"winner_id": winner_mid, "a_score": 27, "b_score": 27},
        headers=_h(director["token"]), timeout=15)
    assert rep.status_code == 200, rep.text
    resolved_bracket = rep.json()["bracket"]
    m = resolved_bracket["tiers"][0][0]
    assert m["winner_id"] == winner_mid
    assert m["a_score"] == 27 and m["b_score"] == 27

    # Idempotent replay — same body, no-op
    rep2 = requests.post(f"{BASE_URL}/api/bracket/matches/{match_id}/report",
        json={"winner_id": winner_mid, "a_score": 27, "b_score": 27},
        headers=_h(director["token"]), timeout=15)
    assert rep2.status_code == 200
    assert rep2.json().get("already_reported") is True
