"""Iteration 57 — Payout Curve Presets.

Verifies the league-level `payout_curve` setting:
  1) Default is [0.5, 0.3, 0.2] on newly created leagues.
  2) `PATCH /api/leagues/{id}/payout-curve` accepts a valid preset (60/25/15)
     and rejects a shape whose shares don't sum to ~1.0.
  3) Non-directors get 403 on the PATCH.
  4) `GET /api/rounds/{id}/payout` respects the league's saved curve —
     switching from 50/30/20 to 60/25/15 shifts the top-3 payouts to
     $60/$25/$15 on a $100 division pool.
  5) The response includes `payout_curve` so the client can drive
     share-card copy without a second call.
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
def _run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i57_{uuid.uuid4().hex[:10]}@example.com"
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
        "name": f"Curve Preset {uuid.uuid4().hex[:6]}",
        "format": "Singles", "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _new_round(director, league_id):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
                            headers=_h(director["token"]), timeout=15).json()
    payload = {
        "name": "Curve W1", "date": "2026-02-15", "holes": 3,
        "par_per_hole": [3, 3, 3], "course_location": "Test Course",
    }
    if seasons: payload["season_id"] = seasons[0]["id"]
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/rounds",
        json=payload, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _credit_pool(director, league_id, amount, round_id):
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/ledger",
        json={"kind": "credit", "category": "Weekly Payout",
              "amount": amount, "note": "test pool", "round_id": round_id},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text


async def _seed(members, scorecards):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.league_members.insert_many(members)
    await db.scorecards.insert_many(scorecards)
    client.close()


def _mk_member(league_id, name, division):
    return {
        "id": uuid.uuid4().hex, "league_id": league_id,
        "user_id": uuid.uuid4().hex, "name": name, "role": "player",
        "division": division, "bag_tag": 999, "priority_tier": False,
    }


def _mk_scorecard(league_id, round_id, member_id, total):
    return {
        "id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
        "member_id": member_id, "scores": [total, 0, 0], "total": total,
        "plus_minus": 0, "handicap_at_round": 0, "finalized": True,
    }


def test_league_defaults_to_50_30_20_curve():
    """A newly-created league must default to the 50/30/20 curve so
    upgrading existing leagues doesn't change their payout math."""
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    a = _mk_member(lg["id"], "A", "Open")
    b = _mk_member(lg["id"], "B", "Open")
    c = _mk_member(lg["id"], "C", "Open")
    _run(_seed([a, b, c], [
        _mk_scorecard(lg["id"], rd["id"], a["id"], 3),
        _mk_scorecard(lg["id"], rd["id"], b["id"], 4),
        _mk_scorecard(lg["id"], rd["id"], c["id"], 5),
    ]))
    _credit_pool(director, lg["id"], 100.0, rd["id"])

    data = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/payout",
                         headers=_h(director["token"]), timeout=15).json()
    # Response carries the curve for client rendering.
    assert data["payout_curve"] == [0.5, 0.3, 0.2]
    payouts = sorted([p["payout"] for p in data["divisions"]["Open"]["players"]], reverse=True)
    assert payouts == [50.0, 30.0, 20.0]


def test_patch_curve_switches_payout_math_to_60_25_15():
    """Saving 60/25/15 must reshape a $100 pool to $60/$25/$15."""
    director = _signup()
    lg = _new_league(director)
    # Switch curve BEFORE seeding scorecards — order shouldn't matter,
    # but we do it first to prove the read-side pulls it fresh.
    r = requests.patch(f"{BASE_URL}/api/leagues/{lg['id']}/payout-curve",
        json={"payout_curve": [0.6, 0.25, 0.15]},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["payout_curve"] == [0.6, 0.25, 0.15]

    rd = _new_round(director, lg["id"])
    a = _mk_member(lg["id"], "A", "Open")
    b = _mk_member(lg["id"], "B", "Open")
    c = _mk_member(lg["id"], "C", "Open")
    _run(_seed([a, b, c], [
        _mk_scorecard(lg["id"], rd["id"], a["id"], 3),
        _mk_scorecard(lg["id"], rd["id"], b["id"], 4),
        _mk_scorecard(lg["id"], rd["id"], c["id"], 5),
    ]))
    _credit_pool(director, lg["id"], 100.0, rd["id"])

    data = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/payout",
                         headers=_h(director["token"]), timeout=15).json()
    assert data["payout_curve"] == [0.6, 0.25, 0.15]
    payouts = sorted([p["payout"] for p in data["divisions"]["Open"]["players"]], reverse=True)
    assert payouts == [60.0, 25.0, 15.0]


def test_patch_curve_rejects_invalid_sum():
    """Shares that don't sum to ~1.0 must be rejected with 400."""
    director = _signup()
    lg = _new_league(director)
    r = requests.patch(f"{BASE_URL}/api/leagues/{lg['id']}/payout-curve",
        json={"payout_curve": [0.5, 0.3]},  # sums to 0.8 — bad
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 400
    assert "sum" in r.json()["detail"].lower()


def test_patch_curve_rejects_non_director():
    """Non-director members can't change the payout curve."""
    director = _signup()
    lg = _new_league(director)
    # Second user joins as a normal player.
    joiner = _signup()
    j = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join", json={},
                       headers=_h(joiner["token"]), timeout=15)
    assert j.status_code == 200, j.text
    r = requests.patch(f"{BASE_URL}/api/leagues/{lg['id']}/payout-curve",
        json={"payout_curve": [0.6, 0.25, 0.15]},
        headers=_h(joiner["token"]), timeout=15)
    assert r.status_code == 403


def test_custom_curve_of_arbitrary_length_is_honoured():
    """A custom 4-slot curve (e.g. 40/30/20/10) must apply to a 4-player
    division and pay out $40/$30/$20/$10 on a $100 pool."""
    director = _signup()
    lg = _new_league(director)
    r = requests.patch(f"{BASE_URL}/api/leagues/{lg['id']}/payout-curve",
        json={"payout_curve": [0.4, 0.3, 0.2, 0.1]},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200

    rd = _new_round(director, lg["id"])
    members = [_mk_member(lg["id"], f"P{i}", "Open") for i in range(4)]
    scs = [
        _mk_scorecard(lg["id"], rd["id"], members[i]["id"], 3 + i)
        for i in range(4)
    ]
    _run(_seed(members, scs))
    _credit_pool(director, lg["id"], 100.0, rd["id"])

    data = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/payout",
                         headers=_h(director["token"]), timeout=15).json()
    payouts = sorted([p["payout"] for p in data["divisions"]["Open"]["players"]], reverse=True)
    assert payouts == [40.0, 30.0, 20.0, 10.0]
