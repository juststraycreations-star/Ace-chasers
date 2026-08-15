"""Iteration 61 — Delete League shadow/audit trail.

Verifies that `DELETE /api/leagues/{id}` now writes a shadow row into
`deleted_leagues` before the cascade sweep runs, and that the row:
  1) Clones the full league configuration snapshot as it was at
     deletion time.
  2) Carries `deletedAt`, `actorId`, and `perCollectionCounts`
     (camelCase aliases for the client) plus their snake_case twins.
  3) Is `retention_locked: true` and has a `restorable_until` timestamp
     roughly 30 days in the future so a future undo path can query it.
  4) Is discoverable by the actor via `GET /api/deleted-leagues` and
     scoped to that actor only.
"""
from __future__ import annotations
import os
import uuid
import time
import asyncio
import pytest
import requests
from datetime import datetime, timezone
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
        email = f"TEST_i61_{uuid.uuid4().hex[:10]}@example.com"
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
        "name": name or f"Shadow {uuid.uuid4().hex[:6]}",
        "format": "Singles", "location": "Test Course",
    }, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


async def _fetch_shadow(league_id):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    doc = await db.deleted_leagues.find_one({"league_id": league_id}, {"_id": 0})
    client.close()
    return doc


def test_shadow_row_is_written_with_full_audit_payload():
    director = _signup()
    original_name = f"Retro {uuid.uuid4().hex[:6]}"
    lg = _new_league(director, name=original_name)
    r = requests.delete(
        f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": original_name},
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Response now surfaces the audit id + restore window.
    assert body["audit_id"]
    assert body["deletedAt"]
    assert body["restorable_until"]

    shadow = _run(_fetch_shadow(lg["id"]))
    assert shadow is not None, "shadow row missing from deleted_leagues"

    # 1) League config snapshot preserved as it was pre-delete.
    assert shadow["league"]["id"] == lg["id"]
    assert shadow["league"]["name"] == original_name

    # 2) Audit fields — both snake_case (persisted) and camelCase (client).
    assert shadow["deleted_at"] and shadow["deletedAt"] == shadow["deleted_at"]
    assert shadow["actor_id"] == director["profile"]["uid"]
    assert shadow["actorId"] == shadow["actor_id"]
    counts = shadow["per_collection_counts"]
    assert counts == shadow["perCollectionCounts"]
    # Counts must include every league-scoped collection we swept plus
    # the league doc itself. The director's membership row is always ≥1.
    for key in ("league_members", "rounds", "scorecards", "seasons",
                "brackets", "ledger", "announcements", "lost_found",
                "stories", "feed_posts", "ctp_entries", "leagues"):
        assert key in counts, f"missing per-collection count for {key}"
    assert counts["leagues"] == 1

    # 3) Retention lock + restore window (~30 days).
    assert shadow["retention_locked"] is True
    ru = datetime.fromisoformat(shadow["restorable_until"])
    delta_days = (ru - datetime.now(timezone.utc)).days
    assert 25 <= delta_days <= 31, f"restore window off: {delta_days}d"
    assert shadow["restore_state"] == "pending"


def test_get_deleted_leagues_returns_only_actor_rows():
    """A director should only see the shadow rows they themselves
    created — never another director's audit trail."""
    dir_a = _signup()
    lg_a = _new_league(dir_a, name=f"OnlyA-{uuid.uuid4().hex[:6]}")
    dir_b = _signup()
    lg_b = _new_league(dir_b, name=f"OnlyB-{uuid.uuid4().hex[:6]}")

    # Both directors delete their own league.
    r1 = requests.delete(f"{BASE_URL}/api/leagues/{lg_a['id']}",
        json={"confirm_name": lg_a["name"]}, headers=_h(dir_a["token"]), timeout=15)
    r2 = requests.delete(f"{BASE_URL}/api/leagues/{lg_b['id']}",
        json={"confirm_name": lg_b["name"]}, headers=_h(dir_b["token"]), timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200

    # Director A sees A's row, not B's.
    listing_a = requests.get(f"{BASE_URL}/api/deleted-leagues",
                              headers=_h(dir_a["token"]), timeout=15).json()
    ids_a = {row["league_id"] for row in listing_a["rows"]}
    assert lg_a["id"] in ids_a
    assert lg_b["id"] not in ids_a
    # Director B sees B's row, not A's.
    listing_b = requests.get(f"{BASE_URL}/api/deleted-leagues",
                              headers=_h(dir_b["token"]), timeout=15).json()
    ids_b = {row["league_id"] for row in listing_b["rows"]}
    assert lg_b["id"] in ids_b
    assert lg_a["id"] not in ids_b


def test_shadow_row_survives_when_league_doc_is_gone():
    """After the cascade, the leagues collection has no row but the
    shadow copy remains queryable — proving the audit trail decouples
    from the live data."""
    director = _signup()
    lg = _new_league(director)
    r = requests.delete(f"{BASE_URL}/api/leagues/{lg['id']}",
        json={"confirm_name": lg["name"]},
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    # League doc is gone.
    gone = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}",
                        headers=_h(director["token"]), timeout=15)
    assert gone.status_code == 404
    # Shadow row is still there.
    shadow = _run(_fetch_shadow(lg["id"]))
    assert shadow is not None
    assert shadow["league"]["id"] == lg["id"]
    assert shadow["retention_locked"] is True
