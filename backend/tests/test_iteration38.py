"""Iteration 38 — Bracket + team scramble + Phase-4 extraction verification.

Covers:
 1) Match Play format bracket
    - Seed with 4 members → 2 tier-0 matches + 1 tier-1 final
    - Report a match → winner stamped, next-tier slot populated
    - Idempotent replay of the same report
    - Non-power-of-2 seeding creates byes (a=member, b=None, auto-winner)
 2) Team scramble
    - PATCH /api/cards/{id}/scramble-score fans out ONE score to every
      scorecard on the card
    - Idempotent replay via Idempotency-Key header returns cached response
      and does not create a second proof_logs row per scorecard
    - Director toggle via PATCH /api/cards/{id}/scramble-mode
 3) Phase-4 extraction sanity
    - /scorecards/{id}/score, /proof, /finalize, /certify still respond
      as expected (they now live in leagues_rounds_router.py)
"""
from __future__ import annotations
import os
import uuid
import asyncio
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup():
    email = f"TEST_i38_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(IDENTITY_SIGNUP,
        json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
    assert r.status_code == 200
    tok = r.json()["idToken"]
    prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
    assert prof.status_code == 200
    return {"token": tok, "profile": prof.json()}


def _mkleague(token, fmt="Match Play"):
    r = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"TEST_i38_{uuid.uuid4().hex[:6]}", "location": "T",
              "format": fmt, "entry_fee": 0.0}, headers=_h(token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ────────────────────────────────────────────────────────────────
# ITEM 1 — Bracket seeding + reporting
# ────────────────────────────────────────────────────────────────
def test_bracket_seed_and_report_flow():
    director = _signup()
    lg = _mkleague(director["token"], fmt="Match Play")
    # 4 members → 2 tier-0 matches + 1 tier-1 final
    m_ids = []
    for _ in range(4):
        u = _signup()
        r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
            headers=_h(u["token"]), timeout=15)
        assert r.status_code == 200
        m_ids.append(r.json()["id"])
    seed = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/bracket/seed",
        json={"member_ids": m_ids}, headers=_h(director["token"]), timeout=15)
    assert seed.status_code == 200, seed.text
    bracket = seed.json()
    assert len(bracket["tiers"]) == 2
    assert len(bracket["tiers"][0]) == 2  # 2 tier-0 matches
    assert len(bracket["tiers"][1]) == 1  # 1 final

    # Report tier-0 match 1
    match0 = bracket["tiers"][0][0]
    winner_id = match0["a_member_id"]
    r = requests.post(
        f"{BASE_URL}/api/bracket/matches/{match0['id']}/report",
        json={"winner_id": winner_id, "a_score": 50, "b_score": 55},
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["already_reported"] is False
    # Winner should be seated into the final's a-slot (advances_to_slot='a')
    updated_final = body["bracket"]["tiers"][1][0]
    assert updated_final[f"{match0['advances_to_slot']}_member_id"] == winner_id

    # Idempotent replay
    r2 = requests.post(
        f"{BASE_URL}/api/bracket/matches/{match0['id']}/report",
        json={"winner_id": winner_id},
        headers=_h(director["token"]), timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json()["already_reported"] is True


def test_bracket_bye_for_non_power_of_two():
    director = _signup()
    lg = _mkleague(director["token"], fmt="Match Play")
    m_ids = []
    for _ in range(3):
        u = _signup()
        r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
            headers=_h(u["token"]), timeout=15)
        m_ids.append(r.json()["id"])
    seed = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/bracket/seed",
        json={"member_ids": m_ids}, headers=_h(director["token"]), timeout=15).json()
    # Should have 2 tier-0 matches (padded to 4 slots)
    assert len(seed["tiers"][0]) == 2
    # Exactly one match should have a bye (b_member_id=None) and pre-set winner
    byes = [m for m in seed["tiers"][0] if m["b_member_id"] is None]
    assert len(byes) == 1
    assert byes[0]["winner_id"] == byes[0]["a_member_id"]


# ────────────────────────────────────────────────────────────────
# ITEM 2 — Team scramble one-score fanout
# ────────────────────────────────────────────────────────────────
def test_scramble_score_fans_out_to_all_teammates():
    director = _signup()
    lg = _mkleague(director["token"], fmt="Team")
    # 2 additional players
    p2 = _signup()
    p3 = _signup()
    for u in (p2, p3):
        r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
            headers=_h(u["token"]), timeout=15)
        assert r.status_code == 200

    # Create a round + one card with all 3 teammates
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(director["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "S1", "date": "2026-05-01",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(director["token"]), timeout=15).json()
    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
        headers=_h(director["token"]), timeout=15).json()
    mem_ids = [m["id"] for m in members]
    card = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/cards",
        json={"label": "Team A", "player_ids": mem_ids},
        headers=_h(director["token"]), timeout=15).json()

    # Post ONE scramble score for hole 3
    key = f"i38-{uuid.uuid4().hex}"
    r = requests.patch(
        f"{BASE_URL}/api/cards/{card['id']}/scramble-score",
        json={"hole": 3, "strokes": 2},
        headers={**_h(director["token"]), "Idempotency-Key": key},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated_count"] == 3

    # Every scorecard on the card should now have strokes=2 on hole 3
    detail = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}",
        headers=_h(director["token"]), timeout=15).json()
    hole3_scores = [sc["scores"][2] for sc in detail["scorecards"] if sc["card_id"] == card["id"]]
    assert hole3_scores == [2, 2, 2]

    # Idempotent replay returns cached response and does NOT create
    # a second proof_log row per scorecard.
    r2 = requests.patch(
        f"{BASE_URL}/api/cards/{card['id']}/scramble-score",
        json={"hole": 3, "strokes": 9},  # different value — must be IGNORED
        headers={**_h(director["token"]), "Idempotency-Key": key},
        timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json() == body

    # Verify no double-log
    async def _proof_count(round_id):
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        n = await db.proof_logs.count_documents({"round_id": round_id, "hole": 3})
        client.close()
        return n
    n = _run(_proof_count(rd["id"]))
    assert n == 3, f"expected 3 proof_logs (one per teammate), got {n}"


def test_scramble_mode_toggle_director_only():
    director = _signup()
    other = _signup()
    lg = _mkleague(director["token"], fmt="Team")
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
        headers=_h(other["token"]), timeout=15)
    assert r.status_code == 200
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(director["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "S2", "date": "2026-05-08",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(director["token"]), timeout=15).json()
    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
        headers=_h(director["token"]), timeout=15).json()
    card = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/cards",
        json={"label": "T", "player_ids": [m["id"] for m in members]},
        headers=_h(director["token"]), timeout=15).json()

    # Non-director → 403
    r = requests.patch(f"{BASE_URL}/api/cards/{card['id']}/scramble-mode",
        json={"scramble_mode": True}, headers=_h(other["token"]), timeout=15)
    assert r.status_code == 403
    # Director → 200
    r = requests.patch(f"{BASE_URL}/api/cards/{card['id']}/scramble-mode",
        json={"scramble_mode": True}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    assert r.json()["scramble_mode"] is True


# ────────────────────────────────────────────────────────────────
# ITEM 4 — Phase 4 extraction sanity (moved scorecard endpoints)
# ────────────────────────────────────────────────────────────────
def test_phase4_moved_scorecard_endpoints_still_work():
    director = _signup()
    lg = _mkleague(director["token"], fmt="Singles")
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(director["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "P4", "date": "2026-05-15",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(director["token"]), timeout=15).json()
    j = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join",
        headers=_h(director["token"]), timeout=15)
    sc_id = j.json()["scorecard"]["id"]

    # score (moved)
    r = requests.patch(f"{BASE_URL}/api/scorecards/{sc_id}/score",
        json={"hole": 1, "strokes": 3}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    # proof (moved)
    r = requests.get(f"{BASE_URL}/api/scorecards/{sc_id}/proof",
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) >= 1
    # certify (moved) — player self-cert
    r = requests.post(f"{BASE_URL}/api/scorecards/{sc_id}/certify",
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    # finalize (moved) — requires certified=true
    r = requests.post(f"{BASE_URL}/api/scorecards/{sc_id}/finalize",
        json={"certified": True}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    assert r.json()["finalized"] is True
