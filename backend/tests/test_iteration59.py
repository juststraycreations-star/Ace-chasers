"""Iteration 59 — Delete League cascade sweep.

Verifies `DELETE /api/leagues/{id}`:
  1) Rejects a wrong `confirm_name` with 400.
  2) Rejects non-director callers with 403.
  3) On success, wipes the league doc + every league-scoped collection
     that carries a `league_id` reference, plus round-scoped
     `ctp_entries` under the deleted rounds. Returns per-collection
     deletion counts.
  4) Idempotent-adjacent: subsequent GETs on the deleted league return
     404 so no stale data lingers on the dashboard.
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
        email = f"TEST_i59_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def _new_league(director, name=None):
    r = requests.post(f"{BASE_URL}/api/leagues", json={
        "name": name or f"Delete Test {uuid.uuid4().hex[:6]}",
        "format": "Singles", "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _new_round(director, league_id):
    seasons = requests.get(f"{BASE_URL}/api/leagues/{league_id}/seasons",
                            headers=_h(director["token"]), timeout=15).json()
    payload = {
        "name": "W1", "date": "2026-02-15", "holes": 3,
        "par_per_hole": [3, 3, 3], "course_location": "Test",
    }
    if seasons: payload["season_id"] = seasons[0]["id"]
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/rounds",
        json=payload, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_extra(league_id, round_id):
    """Drop a scorecard, a ledger entry, a feed post, an announcement,
    and a CTP entry into the league so the cascade has something to
    sweep beyond just the seed docs create_league already made."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.scorecards.insert_one({
        "id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
        "member_id": uuid.uuid4().hex, "total": 3, "plus_minus": 0,
        "scores": [3, 0, 0], "finalized": False,
    })
    await db.ledger.insert_one({
        "id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
        "kind": "credit", "category": "Weekly Payout", "amount": 25.0,
        "note": "seed", "created_at": "2026-02-15T00:00:00Z",
    })
    await db.feed_posts.insert_one({
        "id": uuid.uuid4().hex, "league_id": league_id, "author_id": "seed",
        "text": "hello", "pinned": False, "created_at": "2026-02-15T00:00:00Z",
    })
    await db.announcements.insert_one({
        "id": uuid.uuid4().hex, "league_id": league_id, "title": "seed",
        "body": "hi", "created_at": "2026-02-15T00:00:00Z",
    })
    await db.ctp_entries.insert_one({
        "id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
        "hole": 1, "member_id": uuid.uuid4().hex, "feet": 10, "inches": 0.0,
        "created_at": "2026-02-15T00:00:00Z",
    })
    client.close()


def test_delete_rejects_wrong_confirmation_name():
    director = _signup()
    lg = _new_league(director, name="Alpha Test League")
    r = requests.delete(
        f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": "Wrong Name"},
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 400
    assert "match" in r.json()["detail"].lower()
    # The league must still exist after a rejected delete.
    check = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}",
                         headers=_h(director["token"]), timeout=15)
    assert check.status_code == 200


def test_delete_rejects_non_director():
    director = _signup()
    lg = _new_league(director)
    joiner = _signup()
    j = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/join", json={},
                      headers=_h(joiner["token"]), timeout=15)
    assert j.status_code == 200
    r = requests.delete(
        f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(joiner["token"]), timeout=15,
    )
    assert r.status_code == 403


def test_delete_cascades_across_all_league_scoped_collections():
    director = _signup()
    lg = _new_league(director, name=f"Cascade {uuid.uuid4().hex[:6]}")
    rd = _new_round(director, lg["id"])
    _run(_seed_extra(lg["id"], rd["id"]))

    r = requests.delete(
        f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    counts = body["deleted_counts"]
    # League doc itself removed.
    assert counts["leagues"] == 1
    # Rounds + seasons removed (create_league seeds one season, we made one round).
    assert counts["rounds"] >= 1
    assert counts["seasons"] >= 1
    # Our directly-seeded rows must be gone.
    assert counts["scorecards"] >= 1
    assert counts["ledger"] >= 1
    assert counts["feed_posts"] >= 1
    assert counts["announcements"] >= 1
    assert counts["ctp_entries"] >= 1
    # Director's own membership row was cleaned.
    assert counts["league_members"] >= 1
    # Total is the sum of the parts.
    assert body["total_docs_removed"] == sum(counts.values())

    # GET on the deleted league now 404s.
    gone = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}",
                        headers=_h(director["token"]), timeout=15)
    assert gone.status_code == 404


def test_second_delete_after_success_returns_404():
    """Once a league is deleted, calling DELETE again must 404 — the
    frontend has already navigated away, but we defend against retries."""
    director = _signup()
    lg = _new_league(director)
    r1 = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15)
    assert r1.status_code == 200
    r2 = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15)
    assert r2.status_code == 404
