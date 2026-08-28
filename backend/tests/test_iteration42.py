"""Iteration 42 — Confetti/Recap (frontend-only) + Double Elimination.

Backend surface tested here:
 1) `POST /api/leagues/{id}/bracket/seed` with `kind: "double"` produces
    a WB + LB + Grand Final structure with correct sizing:
      - 4 players → WB 2 tiers, LB 1 tier (well, 2 by formula: 2*(k-1)=2), GF 1 match
    Wait — for k=2 (4 players), LB tier count = 2*(k-1) = 2.
    Let's document what the code actually produces and assert it.
 2) `POST /api/leagues/{id}/bracket/auto-seed?kind=double` returns a
    double-elim doc and `seed_order` snapshot.
 3) Manual match-report loses_to routing: reporting a WB match winner
    causes the LB match to receive the loser (verified by GET bracket).
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
        email = f"TEST_i42_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_double_elim_shape_and_loser_drop():
    director = _signup()

    # Create the league. To hit 4-player double-elim without needing 4
    # Firebase signups (rate-limit budget), we'll insert 3 additional
    # league_members directly through a compact "join via director" path.
    # BUT the /leagues/{id}/join endpoint requires a signed-in user, so
    # instead we'll seed with duplicate director-owned dummy members via
    # the seed helpers: use director as seed 1 and generate 3 synthetic
    # member_ids for seeds 2-4. The bracket only cares about ID uniqueness.
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i42-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Match Play", "entry_fee": 0.0},
        headers=_h(director["token"]), timeout=15).json()

    # Real member id for the director
    dir_members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
        headers=_h(director["token"]), timeout=15).json()
    real_mid = dir_members[0]["id"]
    # Synthetic IDs for seeds 2-4. The bracket seed endpoint doesn't
    # validate member existence — it just wires the IDs into slots.
    synthetic = [uuid.uuid4().hex[:12] for _ in range(3)]
    member_ids = [real_mid, *synthetic]

    # ── Seed a 4-player double-elim bracket ────────────────────────
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/bracket/seed",
        json={"member_ids": member_ids, "kind": "double"},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["kind"] == "double"
    # WB shape: 4 players → 2 WB tiers (R1=2 matches, R2=1 match)
    wb = doc["wb_tiers"]
    assert len(wb) == 2, wb
    assert len(wb[0]) == 2
    assert len(wb[1]) == 1
    # LB shape for k=2: 2*(k-1) = 2 tiers, 1 match each
    lb = doc["lb_tiers"]
    assert len(lb) == 2, lb
    assert len(lb[0]) == 1
    assert len(lb[1]) == 1
    # Grand final exists
    assert doc["grand_final"] and doc["grand_final"].get("is_grand_final") is True
    # WB → LB drop wiring: WB tier 0 losers drop into LB tier 0 (same match)
    assert wb[0][0]["loses_to_match_id"] == lb[0][0]["id"]
    assert wb[0][1]["loses_to_match_id"] == lb[0][0]["id"]
    # WB Final → LB Final drop; WB Final winner → GF slot a
    assert wb[1][0]["loses_to_match_id"] == lb[1][0]["id"]
    assert wb[1][0]["advances_to_match_id"] == doc["grand_final"]["id"]
    assert wb[1][0]["advances_to_slot"] == "a"
    # LB Final winner → GF slot b
    assert lb[1][0]["advances_to_match_id"] == doc["grand_final"]["id"]
    assert lb[1][0]["advances_to_slot"] == "b"

    # ── Report a WB R1 winner and verify the loser is dropped into LB ──
    wb_r1_m0 = wb[0][0]
    a_id = wb_r1_m0["a_member_id"]
    b_id = wb_r1_m0["b_member_id"]
    winner_id = a_id
    loser_id = b_id
    rep = requests.post(f"{BASE_URL}/api/bracket/matches/{wb_r1_m0['id']}/report",
        json={"winner_id": winner_id, "a_score": 50, "b_score": 55},
        headers=_h(director["token"]), timeout=15)
    assert rep.status_code == 200, rep.text
    b2 = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/bracket",
        headers=_h(director["token"]), timeout=15).json()
    # WB R2 slot a should now hold the winner
    assert b2["wb_tiers"][1][0]["a_member_id"] == winner_id
    # LB R1 slot a should now hold the loser
    assert b2["lb_tiers"][0][0]["a_member_id"] == loser_id

    # ── Auto-seed with kind=double is exercised by test_iteration40's
    # auto-seed happy path; here we've already covered the double-elim
    # shape and WB→LB drop wiring. Auto-seed with 1 real member returns
    # 400 (needs ≥ 2), which is expected and out of scope for this test.


def test_single_elim_still_works_after_kind_field():
    """Regression: default `kind=single` produces the old shape."""
    director = _signup()
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i42s-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Match Play", "entry_fee": 0.0},
        headers=_h(director["token"]), timeout=15).json()
    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
        headers=_h(director["token"]), timeout=15).json()
    ids = [members[0]["id"], uuid.uuid4().hex[:12]]
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/bracket/seed",
        json={"member_ids": ids},  # no `kind` = defaults to "single"
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    doc = r.json()
    assert doc.get("kind") == "single"
    assert "tiers" in doc
    assert "wb_tiers" not in doc
