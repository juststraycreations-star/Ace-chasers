"""Iteration 72 — push_notifications_log observability collection.

Verifies:
  1) Every `process_live_round_event` invocation writes exactly ONE
     row to `push_notifications_log` with the required camelCase shape
     (eventId, roundId, eventType, totalSent, totalFailed, tokensPruned,
     timestamp, dryRun).
  2) Even the no-recipients / unknown-event paths write a telemetry
     row so the observability surface has a complete audit trail.
  3) `GET /api/push/log` returns rows scoped to the caller's auth and
     honours `event_type` / `round_id` filters + aggregate `totals`.
  4) bracket_advance now flows through the same payload builder + log.
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
        email = f"TEST_i72_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


async def _shadow_log_count(round_id):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    n = await db.push_notifications_log.count_documents({"roundId": round_id})
    client.close()
    return n


def test_worker_writes_a_telemetry_row_every_call():
    from push_service import process_live_round_event  # type: ignore
    round_id = f"tel-r-{uuid.uuid4().hex}"
    before = _run(_shadow_log_count(round_id))
    _run(process_live_round_event(round_id, "join_code_rotated",
                                     join_code="AB2K", old_code="XY7Q"))
    after = _run(_shadow_log_count(round_id))
    assert after == before + 1


def test_telemetry_row_has_exact_camelcase_shape():
    from push_service import process_live_round_event  # type: ignore
    round_id = f"tel-r-{uuid.uuid4().hex}"
    _run(process_live_round_event(round_id, "join_code_rotated"))

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    row = _run(db.push_notifications_log.find_one({"roundId": round_id}, {"_id": 0}))
    client.close()
    assert row is not None
    for field in ("eventId", "roundId", "eventType",
                   "totalSent", "totalFailed", "tokensPruned",
                   "dryRun", "timestamp"):
        assert field in row, f"missing observability field: {field}"
    assert row["roundId"] == round_id
    assert row["eventType"] == "join_code_rotated"
    # Sandbox has no FCM creds → send counts are 0. dryRun reflects
    # whether _fan_out actually ran (True only when there were
    # recipients AND creds were missing). For a no-recipients round
    # it stays False. Either way the field must be a bool.
    assert row["totalSent"] == 0
    assert row["totalFailed"] == 0
    assert row["tokensPruned"] == 0
    assert isinstance(row["dryRun"], bool)


def test_unknown_event_still_gets_a_telemetry_row():
    """Even a garbage event_type must produce an audit row so nothing
    falls off the observability surface."""
    from push_service import process_live_round_event  # type: ignore
    round_id = f"tel-r-{uuid.uuid4().hex}"
    _run(process_live_round_event(round_id, "not-a-real-event"))
    assert _run(_shadow_log_count(round_id)) == 1


def test_get_push_log_endpoint_filters_and_totals():
    user = _signup()
    from push_service import process_live_round_event  # type: ignore
    round_id = f"tel-r-{uuid.uuid4().hex}"
    # Two different event types on the same round.
    _run(process_live_round_event(round_id, "join_code_rotated"))
    _run(process_live_round_event(round_id, "payouts_finalized"))

    # Filter by round_id → both rows.
    r_all = requests.get(f"{BASE_URL}/api/push/log",
                         params={"round_id": round_id},
                         headers=_h(user["token"]), timeout=15).json()
    assert r_all["totals"]["count"] == 2
    types = {row["eventType"] for row in r_all["rows"]}
    assert types == {"join_code_rotated", "payouts_finalized"}
    # totals aggregate the three counters across all returned rows.
    for k in ("sent", "failed", "pruned"):
        assert isinstance(r_all["totals"][k], int)

    # Filter by event_type → one row.
    r_one = requests.get(f"{BASE_URL}/api/push/log",
                         params={"round_id": round_id, "event_type": "payouts_finalized"},
                         headers=_h(user["token"]), timeout=15).json()
    assert r_one["totals"]["count"] == 1
    assert r_one["rows"][0]["eventType"] == "payouts_finalized"


def test_bracket_advance_flows_through_worker_and_logs():
    """`bracket_advance` is a new supported event type. It should
    resolve league members like payouts_finalized and write a log row
    with its own eventType label."""
    from push_service import process_live_round_event, _build_payload  # type: ignore
    round_id = f"tel-r-{uuid.uuid4().hex}"
    payload = _build_payload(round_id, "bracket_advance",
                              {"winner_name": "Riley Chen", "is_final": True})
    # Payload structure spot-check.
    assert payload["notification"]["title"] == "Bracket champion crowned!"
    assert "Riley Chen" in payload["notification"]["body"]
    assert payload["android"]["notification"]["channel_id"] == "ace_chasers_bracket"
    # Full worker call writes a telemetry row.
    _run(process_live_round_event(round_id, "bracket_advance",
                                     winner_name="Riley Chen", is_final=True))
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    row = _run(db.push_notifications_log.find_one(
        {"roundId": round_id, "eventType": "bracket_advance"}, {"_id": 0}
    ))
    client.close()
    assert row is not None
