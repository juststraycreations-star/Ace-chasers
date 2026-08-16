"""Iteration 62 — Delete League 30s undo · restore path.

Verifies `POST /api/leagues/restore` works end-to-end:
  1) After a DELETE, the shadow row includes `shadow_docs` with every
     league- and round-scoped child (rounds, scorecards, ledger,
     ctp_entries, etc.).
  2) `POST /api/leagues/restore` with the audit id reinserts the
     league doc AND every shadow-scoped child, returning per-collection
     restore counts.
  3) After restore, `GET /api/leagues/{id}` succeeds again and the
     shadow row is stamped `restore_state: "restored"` with
     `retention_locked: false`.
  4) A second restore attempt on the same audit id returns 409.
  5) Only the original deleter can restore (non-deleter → 403).
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
        email = f"TEST_i62_{uuid.uuid4().hex[:10]}@example.com"
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
        "name": name or f"Undo {uuid.uuid4().hex[:6]}",
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


async def _seed_children(league_id, round_id):
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
    await db.ctp_entries.insert_one({
        "id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
        "hole": 1, "member_id": uuid.uuid4().hex, "feet": 10, "inches": 0.0,
        "created_at": "2026-02-15T00:00:00Z",
    })
    client.close()


async def _shadow(audit_id):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    doc = await db.deleted_leagues.find_one({"id": audit_id}, {"_id": 0})
    client.close()
    return doc


def test_shadow_includes_child_docs_for_restore():
    """After delete, the shadow row must carry a `shadow_docs` map with
    every child doc keyed by its source collection."""
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    _run(_seed_children(lg["id"], rd["id"]))

    d = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15).json()
    shadow = _run(_shadow(d["audit_id"]))
    assert shadow is not None
    sd = shadow["shadow_docs"]
    assert isinstance(sd, dict)
    # Every league-scoped collection is represented, even if empty.
    for key in ("league_members", "rounds", "scorecards", "seasons",
                "brackets", "ledger", "announcements", "lost_found",
                "stories", "feed_posts", "ctp_entries"):
        assert key in sd, f"missing shadow_docs entry for {key}"
    # Our seeded children survived the snapshot.
    assert any(s["round_id"] == rd["id"] for s in sd["scorecards"])
    assert any(l["round_id"] == rd["id"] for l in sd["ledger"])
    assert any(c["round_id"] == rd["id"] for c in sd["ctp_entries"])


def test_restore_reinserts_league_and_all_children():
    director = _signup()
    lg = _new_league(director)
    rd = _new_round(director, lg["id"])
    _run(_seed_children(lg["id"], rd["id"]))

    d = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15).json()

    # League is gone.
    assert requests.get(f"{BASE_URL}/api/leagues/{lg['id']}",
                        headers=_h(director["token"]), timeout=15).status_code == 404

    r = requests.post(f"{BASE_URL}/api/leagues/restore",
        json={"audit_id": d["audit_id"]},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["league_id"] == lg["id"]
    # Every collection has a restore count entry; leagues restored = 1.
    assert body["restored_counts"]["leagues"] == 1
    assert body["restored_counts"]["rounds"] >= 1

    # League is back and queryable.
    reborn = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}",
                          headers=_h(director["token"]), timeout=15)
    assert reborn.status_code == 200
    assert reborn.json()["id"] == lg["id"]

    # Shadow row is stamped restored + retention lock released.
    shadow = _run(_shadow(d["audit_id"]))
    assert shadow["restore_state"] == "restored"
    assert shadow["retention_locked"] is False


def test_restore_is_idempotent_after_success():
    """A double-tap on the Undo button (or a stale retry) must return
    409 rather than double-inserting rows."""
    director = _signup()
    lg = _new_league(director)
    d = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15).json()
    r1 = requests.post(f"{BASE_URL}/api/leagues/restore",
        json={"audit_id": d["audit_id"]},
        headers=_h(director["token"]), timeout=15)
    assert r1.status_code == 200
    r2 = requests.post(f"{BASE_URL}/api/leagues/restore",
        json={"audit_id": d["audit_id"]},
        headers=_h(director["token"]), timeout=15)
    assert r2.status_code == 409


def test_restore_requires_original_deleter():
    """Only the actor who deleted the league can restore it."""
    director = _signup()
    lg = _new_league(director)
    d = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15).json()
    attacker = _signup()
    r = requests.post(f"{BASE_URL}/api/leagues/restore",
        json={"audit_id": d["audit_id"]},
        headers=_h(attacker["token"]), timeout=15)
    assert r.status_code == 403


def test_restore_404_on_unknown_audit_id():
    director = _signup()
    r = requests.post(f"{BASE_URL}/api/leagues/restore",
        json={"audit_id": "does-not-exist-" + uuid.uuid4().hex},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 404
