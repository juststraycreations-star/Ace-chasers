"""Iteration 37 — Multi-mode leaderboards, schedule publisher, founder referral.

Covers:
 1) ITEM 1 · GET /api/rounds/{id}/leaderboard
    - Singles league → mode=singles, one row per player
    - Random-Draw Doubles league → mode=best_disc, teams aggregate correctly
      (per-hole MIN across cardmates)
 2) ITEM 2 · POST /api/leagues/{id}/rounds
    - Auto-publishes a pinned FeedPost with kind="schedule"
    - Explicit `publish_announcement: false` suppresses it
 3) ITEM 3 · Founder referral
    - GET /api/users/me/referral mints a stable ref_code
    - POST /api/users/me/redeem-referral stamps `founder_sponsor_by`,
      `priority_tier: true`, and updates existing league_members rows
    - Self-referral 400s; unknown code 404s; second redeem is idempotent
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
IDENTITY_SIGNUP = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
)


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _signup():
    email = f"TEST_i37_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(IDENTITY_SIGNUP,
        json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
    assert r.status_code == 200, r.text
    tok = r.json()["idToken"]
    prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
    assert prof.status_code == 200, prof.text
    return {"token": tok, "profile": prof.json()}


def _mkleague(token, fmt="Singles"):
    r = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"TEST_i37_{uuid.uuid4().hex[:6]}", "location": "Test",
              "format": fmt, "entry_fee": 5.0}, headers=_h(token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _mkround(director_token, league_id, *, name, date, publish=True, course_location=None):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
        headers=_h(director_token), timeout=15).json()
    body = {"name": name, "date": date, "season_id": seasons[0]["id"],
            "holes": 9, "par_per_hole": [3] * 9, "publish_announcement": publish}
    if course_location:
        body["course_location"] = course_location
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/rounds",
        json=body, headers=_h(director_token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ────────────────────────────────────────────────────────────────
# ITEM 2 — Schedule publisher hook
# ────────────────────────────────────────────────────────────────
def test_round_create_publishes_pinned_schedule_post():
    director = _signup()
    lg = _mkleague(director["token"])
    rd = _mkround(director["token"], lg["id"],
                   name=f"R1-{uuid.uuid4().hex[:5]}",
                   date="2026-03-15",
                   course_location="Maple Hill · Leicester, MA")
    # Feed should now contain a pinned schedule post
    feed = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/feed",
        headers=_h(director["token"]), timeout=15).json()
    scheduled = [p for p in feed if p.get("kind") == "schedule"]
    assert scheduled, "expected auto-published schedule post"
    p = scheduled[0]
    assert p["pinned"] is True
    assert "Maple Hill" in p["body"]
    assert p["meta"]["round_id"] == rd["id"]


def test_round_create_can_suppress_announcement():
    director = _signup()
    lg = _mkleague(director["token"])
    _mkround(director["token"], lg["id"],
              name=f"R2-{uuid.uuid4().hex[:5]}",
              date="2026-03-22", publish=False)
    feed = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/feed",
        headers=_h(director["token"]), timeout=15).json()
    assert not any(p.get("kind") == "schedule" for p in feed)


# ────────────────────────────────────────────────────────────────
# ITEM 1 — Singles & Doubles leaderboards
# ────────────────────────────────────────────────────────────────
def test_singles_leaderboard_shape():
    director = _signup()
    lg = _mkleague(director["token"], fmt="Singles")
    rd = _mkround(director["token"], lg["id"],
                   name=f"R-{uuid.uuid4().hex[:5]}", date="2026-04-01")

    # Director self-enrolls (creates a solo card + scorecard)
    j = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/self-enroll",
        headers=_h(director["token"]), timeout=15)
    assert j.status_code == 200
    sc_id = j.json()["scorecard"]["id"]
    # Post a score on hole 1
    r = requests.patch(f"{BASE_URL}/api/scorecards/{sc_id}/score",
        json={"hole": 1, "strokes": 3}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200

    lb = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/leaderboard",
        headers=_h(director["token"]), timeout=15).json()
    assert lb["format"] == "Singles"
    assert lb["mode"] == "singles"
    assert lb["rows"]
    assert lb["rows"][0]["total"] == 3
    assert "member_id" in lb["rows"][0]


def test_doubles_leaderboard_uses_best_disc():
    """Two players on the same card → team total = per-hole MIN across
    both scorecards. Ensures the aggregation logic isn't just summing."""
    director = _signup()
    p2 = _signup()
    lg = _mkleague(director["token"], fmt="Random-Draw Doubles")

    # p2 joins the league
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
        headers=_h(p2["token"]), timeout=15)
    assert r.status_code == 200

    rd = _mkround(director["token"], lg["id"],
                   name=f"D-{uuid.uuid4().hex[:5]}", date="2026-04-08")

    # Get member ids
    members = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/members",
        headers=_h(director["token"]), timeout=15).json()
    mem_ids = [m["id"] for m in members]

    # Director builds one card with both players
    r = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/cards",
        json={"label": "T1", "player_ids": mem_ids},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    # Fetch scorecards
    detail = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}",
        headers=_h(director["token"]), timeout=15).json()
    scs = detail["scorecards"]
    assert len(scs) == 2
    # Sort deterministically by member_id
    scs = sorted(scs, key=lambda s: s["member_id"])
    # Hole 1: player A shoots 4, player B shoots 2 → team best = 2
    requests.patch(f"{BASE_URL}/api/scorecards/{scs[0]['id']}/score",
        json={"hole": 1, "strokes": 4}, headers=_h(director["token"]), timeout=15)
    # Player B has to score on THEIR OWN scorecard — but only the caller
    # who owns each scorecard can write. For test simplicity, director
    # (a league member) is authorized to patch any member's scorecard.
    requests.patch(f"{BASE_URL}/api/scorecards/{scs[1]['id']}/score",
        json={"hole": 1, "strokes": 2}, headers=_h(director["token"]), timeout=15)

    lb = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/leaderboard",
        headers=_h(director["token"]), timeout=15).json()
    assert lb["mode"] == "best_disc", lb
    assert len(lb["rows"]) == 1, lb
    team = lb["rows"][0]
    assert team["total"] == 2, f"expected best-disc min=2, got {team['total']}"
    assert team["combined_scores"][0] == 2


# ────────────────────────────────────────────────────────────────
# ITEM 3 — Founder referral engine
# ────────────────────────────────────────────────────────────────
def test_referral_mint_stable_and_redemption_stamps_priority():
    sponsor = _signup()
    invitee = _signup()

    # Sponsor mints a code
    r = requests.get(f"{BASE_URL}/api/users/me/referral",
        headers=_h(sponsor["token"]), timeout=15)
    assert r.status_code == 200
    code = r.json()["ref_code"]
    assert code and len(code) >= 4

    # Second call returns the same code (idempotent)
    r2 = requests.get(f"{BASE_URL}/api/users/me/referral",
        headers=_h(sponsor["token"]), timeout=15)
    assert r2.json()["ref_code"] == code

    # Invitee redeems
    r3 = requests.post(f"{BASE_URL}/api/users/me/redeem-referral",
        json={"ref_code": code}, headers=_h(invitee["token"]), timeout=15)
    assert r3.status_code == 200, r3.text
    assert r3.json()["already_redeemed"] is False

    # DB assertion: invitee.priority_tier == True
    async def _check(invitee_uid):
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        doc = await db.users.find_one({"uid": invitee_uid})
        client.close()
        return doc

    doc = _run(_check(invitee["profile"]["uid"]))
    assert doc["priority_tier"] is True
    assert doc["founder_sponsor_by"] == sponsor["profile"]["uid"]

    # Idempotent second redeem
    r4 = requests.post(f"{BASE_URL}/api/users/me/redeem-referral",
        json={"ref_code": code}, headers=_h(invitee["token"]), timeout=15)
    assert r4.status_code == 200
    assert r4.json()["already_redeemed"] is True

    # Self-referral rejected
    r5 = requests.post(f"{BASE_URL}/api/users/me/redeem-referral",
        json={"ref_code": code}, headers=_h(sponsor["token"]), timeout=15)
    assert r5.status_code == 400

    # Unknown code rejected
    r6 = requests.post(f"{BASE_URL}/api/users/me/redeem-referral",
        json={"ref_code": "ZZZZZZZZ"}, headers=_h(_signup()["token"]), timeout=15)
    assert r6.status_code == 404


def test_referral_flows_into_league_member_priority():
    """When an already-referred user joins a league AFTER redemption,
    the update_many sweep should have set priority_tier on any existing
    league_members row. Verified by seeding one then redeeming."""
    sponsor = _signup()
    code = requests.get(f"{BASE_URL}/api/users/me/referral",
        headers=_h(sponsor["token"]), timeout=15).json()["ref_code"]

    invitee = _signup()
    lg = _mkleague(sponsor["token"])
    # Invitee joins the sponsor's league FIRST (priority_tier not yet set)
    requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join",
        headers=_h(invitee["token"]), timeout=15)
    # Now redeem — this should retroactively flip priority_tier on the
    # existing league_member row.
    r = requests.post(f"{BASE_URL}/api/users/me/redeem-referral",
        json={"ref_code": code}, headers=_h(invitee["token"]), timeout=15)
    assert r.status_code == 200

    async def _mem(uid, league_id):
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        doc = await db.league_members.find_one({"user_id": uid, "league_id": league_id})
        client.close()
        return doc

    mem = _run(_mem(invitee["profile"]["uid"], lg["id"]))
    assert mem is not None
    assert mem.get("priority_tier") is True
