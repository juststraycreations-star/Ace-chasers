"""Iteration 55 — Payout distribution math for Division Payout Cards.

The Division Payout Cards feature on the client renders one PNG per
division showing projected payouts. It reads `GET /api/rounds/{id}/payout`
and trusts the server to distribute the pool. This test guards the math:

  1) The weekly-payout pool is distributed across divisions proportional
     to # players in each division.
  2) Within each division the top-3 payouts follow a 50/30/20 curve, with
     any rounding remainder folded into first place.
  3) If a division has 2 players, curve degrades to top-2 (no third place).
  4) If a division has 1 player, that player gets 100% of the division pool.

To keep the test cheap on Firebase, we do everything with a single
signup (director-only membership) and seed players by directly writing
`league_members` and `scorecards` rows via Motor. The `/rounds/{id}/payout`
endpoint reads only those two collections plus `ledger`, so the flow is
deterministic without going through the round-join path.
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
        email = f"TEST_i55_{uuid.uuid4().hex[:10]}@example.com"
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
        "name": f"Payout Cards {uuid.uuid4().hex[:6]}",
        "format": "Singles",
        "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _new_round(director, league_id):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
                            headers=_h(director["token"]), timeout=15).json()
    payload = {
        "name": "Payout Week",
        "date": "2026-02-14",
        "holes": 3,
        "par_per_hole": [3, 3, 3],
        "course_location": "Test Course",
    }
    if seasons:
        payload["season_id"] = seasons[0]["id"]
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
        "id": uuid.uuid4().hex,
        "league_id": league_id,
        "user_id": uuid.uuid4().hex,
        "name": name,
        "role": "player",
        "division": division,
        "bag_tag": 999,
        "priority_tier": False,
    }


def _mk_scorecard(league_id, round_id, member_id, total, plus_minus=0):
    scores = [total] + [0, 0]  # arbitrary; endpoint reads only `total`
    return {
        "id": uuid.uuid4().hex,
        "league_id": league_id,
        "round_id": round_id,
        "member_id": member_id,
        "scores": scores,
        "total": total,
        "plus_minus": plus_minus,
        "handicap_at_round": 0,
        "finalized": True,
    }


def test_pool_distributes_proportionally_across_two_divisions():
    """MPO: 3 players, FA: 1 player, pool=$100. MPO gets 75, FA gets 25.
    Within MPO 50/30/20 → 37.50 / 22.50 / 15.00. FA solo → 25.00."""
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    # Seed 3 MPO + 1 FA members and their scorecards.
    mpo1 = _mk_member(lg["id"], "MPO 1st", "MPO")
    mpo2 = _mk_member(lg["id"], "MPO 2nd", "MPO")
    mpo3 = _mk_member(lg["id"], "MPO 3rd", "MPO")
    fa1  = _mk_member(lg["id"], "FA Solo", "FA")
    scs = [
        _mk_scorecard(lg["id"], rd["id"], mpo1["id"], 3),
        _mk_scorecard(lg["id"], rd["id"], mpo2["id"], 4),
        _mk_scorecard(lg["id"], rd["id"], mpo3["id"], 5),
        _mk_scorecard(lg["id"], rd["id"], fa1["id"],  4),
    ]
    _run(_seed([mpo1, mpo2, mpo3, fa1], scs))
    _credit_pool(director, lg["id"], 100.0, rd["id"])

    r = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/payout",
                      headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pool_available"] == 100.0
    mpo = data["divisions"]["MPO"]
    fa  = data["divisions"]["FA"]
    # Pool split proportional to # players: 3/4 * 100 = 75, 1/4 * 100 = 25.
    assert mpo["pool"] == 75.0
    assert fa["pool"] == 25.0
    # MPO 50/30/20 top-3 → 37.50, 22.50, 15.00.
    mpo_payouts = sorted([p["payout"] for p in mpo["players"]], reverse=True)
    assert mpo_payouts == [37.5, 22.5, 15.0]
    # FA solo player takes the whole division pool.
    assert fa["players"][0]["payout"] == 25.0


def test_two_player_division_folds_third_slice_into_first():
    """A division with only 2 players should still use the 50/30 curve
    with the leftover 20% fed into 1st place — the server exposes this
    via the `remaining` fold in leagues_rounds_router.get_payout."""
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    a = _mk_member(lg["id"], "Duo A", "Duo")
    b = _mk_member(lg["id"], "Duo B", "Duo")
    scs = [
        _mk_scorecard(lg["id"], rd["id"], a["id"], 3),
        _mk_scorecard(lg["id"], rd["id"], b["id"], 5),
    ]
    _run(_seed([a, b], scs))
    _credit_pool(director, lg["id"], 100.0, rd["id"])

    data = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/payout",
                        headers=_h(director["token"]), timeout=15).json()
    duo = data["divisions"]["Duo"]
    assert duo["pool"] == 100.0
    payouts = [p["payout"] for p in duo["players"]]
    # 1st gets 50% + folded 20% = 70; 2nd gets 30%.
    assert payouts[0] == 70.0
    assert payouts[1] == 30.0


def test_solo_player_takes_the_entire_pool():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    solo = _mk_member(lg["id"], "Lone Wolf", "Open")
    _run(_seed([solo], [_mk_scorecard(lg["id"], rd["id"], solo["id"], 3)]))
    _credit_pool(director, lg["id"], 50.0, rd["id"])

    data = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}/payout",
                        headers=_h(director["token"]), timeout=15).json()
    open_div = data["divisions"]["Open"]
    assert open_div["pool"] == 50.0
    assert open_div["players"][0]["payout"] == 50.0
