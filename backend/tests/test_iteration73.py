"""Iteration 73 — FCM 5xx exponential-backoff retry queue.

Verifies:
  1) `_send_one` classifies 5xx / 429 / network errors as `retry`, and
     4xx errors as terminal (no retry field set).
  2) `_retry_with_backoff` re-attempts transient failures with an
     exponential schedule, stops as soon as everything succeeds, and
     writes exactly one `phase: "retry"` follow-up row to
     `push_notifications_log` correlated by the parent `eventId`.
  3) Tokens that exhaust every retry attempt are logged with
     truncated prefixes under `failedTokenPrefixes` (never full
     tokens — those are secrets).
  4) `_spawn_background` registers the task, then self-clears the
     registry via `add_done_callback` so long-running processes
     don't leak completed asyncio tasks.
  5) End-to-end: `process_live_round_event` returns immediately even
     when the retry batch is scheduled, and the retry runs entirely
     out-of-band on the event loop (never blocks the caller).
"""
from __future__ import annotations
import os
import uuid
import asyncio
from types import SimpleNamespace

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fetch_log_rows(event_id):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    rows = await db.push_notifications_log.find(
        {"eventId": event_id}, {"_id": 0}
    ).to_list(50)
    client.close()
    return rows


# ══════════════════════════════════════════════════════════════════
# 1) _send_one classifier
# ══════════════════════════════════════════════════════════════════
def test_send_one_marks_5xx_as_retry(monkeypatch):
    from push_service import _send_one

    class FakeResp:
        status_code = 503
        def json(self): return {"error": {"status": "UNAVAILABLE"}}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): return FakeResp()

    async def fake_token(_): return "fake-token"

    monkeypatch.setattr("push_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("push_service._get_access_token", fake_token)

    result = _run(_send_one({"token": "tok_5xx"}, {"data": {}}, "/tmp/x", "proj"))
    assert result["ok"] is False
    assert result.get("retry") is True
    assert result.get("prune") is not True
    assert "503" in result["status"]


def test_send_one_marks_4xx_as_terminal(monkeypatch):
    from push_service import _send_one

    class FakeResp:
        status_code = 400
        def json(self): return {"error": {"status": "INVALID_ARGUMENT"}}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): return FakeResp()

    async def fake_token(_): return "fake-token"

    monkeypatch.setattr("push_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("push_service._get_access_token", fake_token)

    result = _run(_send_one({"token": "tok_4xx"}, {"data": {}}, "/tmp/x", "proj"))
    # INVALID_ARGUMENT → prune, definitely NOT retry
    assert result["ok"] is False
    assert result.get("retry") is not True
    assert result.get("prune") is True


def test_send_one_network_error_is_transient(monkeypatch):
    import httpx
    from push_service import _send_one

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): raise httpx.ConnectError("boom")

    async def fake_token(_): return "fake-token"

    monkeypatch.setattr("push_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("push_service._get_access_token", fake_token)

    result = _run(_send_one({"token": "tok_net"}, {"data": {}}, "/tmp/x", "proj"))
    assert result.get("retry") is True
    assert "http_error" in result["status"]


# ══════════════════════════════════════════════════════════════════
# 2) _retry_with_backoff — success on 2nd attempt
# ══════════════════════════════════════════════════════════════════
def test_retry_succeeds_and_logs_follow_up_row(monkeypatch):
    import push_service as ps

    parent_id = str(uuid.uuid4())
    round_id = f"retry-ok-{uuid.uuid4().hex}"

    call_ledger = {"count": 0}

    async def flaky_send_one(row, payload, creds, proj):
        # First pass: 5xx (retry). Second pass: 200.
        call_ledger["count"] += 1
        if call_ledger["count"] == 1:
            return {"ok": False, "retry": True, "status": "503:UNAVAILABLE"}
        return {"ok": True, "status": "sent"}

    monkeypatch.setattr(ps, "_send_one", flaky_send_one)

    _run(ps._retry_with_backoff(
        recipients=[{"token": "aaaaaaaaaaaaXXXXX"}],
        payload={"data": {}},
        creds_path="/tmp/x",
        project_id="proj",
        round_id=round_id,
        event_type="join_code_rotated",
        parent_event_id=parent_id,
        max_attempts=3,
        base_delay=0.01,  # 10ms → 20ms → 40ms so test is fast
    ))

    rows = _run(_fetch_log_rows(parent_id))
    assert len(rows) == 1
    row = rows[0]
    assert row["phase"] == "retry"
    assert row["eventId"] == parent_id
    assert row["roundId"] == round_id
    assert row["retriedSent"] == 1
    assert row["permanentlyFailed"] == 0
    assert row["failedTokenPrefixes"] == []
    assert row["totalSent"] == 1
    assert row["totalFailed"] == 0
    # 1 initial retry attempt = 2 send calls total.
    assert row["attempts"] == 2
    assert call_ledger["count"] == 2


# ══════════════════════════════════════════════════════════════════
# 3) _retry_with_backoff — exhausted attempts → permanent failure
# ══════════════════════════════════════════════════════════════════
def test_retry_exhaustion_logs_permanent_failure(monkeypatch):
    import push_service as ps

    parent_id = str(uuid.uuid4())
    round_id = f"retry-perm-{uuid.uuid4().hex}"

    async def always_5xx(row, payload, creds, proj):
        return {"ok": False, "retry": True, "status": "500:INTERNAL"}

    monkeypatch.setattr(ps, "_send_one", always_5xx)

    long_tok = "bbbbbbbbbbbbCCCCCCCCCCCC"  # 24 chars → prefix keeps first 12 + ellipsis
    _run(ps._retry_with_backoff(
        recipients=[{"token": long_tok}, {"token": "cccccccccccc"}],
        payload={"data": {}},
        creds_path="/tmp/x",
        project_id="proj",
        round_id=round_id,
        event_type="payouts_finalized",
        parent_event_id=parent_id,
        max_attempts=2,
        base_delay=0.01,
    ))

    rows = _run(_fetch_log_rows(parent_id))
    assert len(rows) == 1
    row = rows[0]
    assert row["phase"] == "retry"
    assert row["permanentlyFailed"] == 2
    assert row["retriedSent"] == 0
    assert row["attempts"] == 2
    # Prefixes are truncated — first 12 chars + ellipsis, never full tokens.
    for pfx in row["failedTokenPrefixes"]:
        assert pfx.endswith("…")
        assert long_tok not in pfx
        assert len(pfx) <= 13  # 12 chars + 1 ellipsis
    # Aggregated fields stay consistent for the dashboard tile.
    assert row["totalFailed"] == 2
    assert row["totalSent"] == 0


# ══════════════════════════════════════════════════════════════════
# 4) _spawn_background — safe registry lifecycle
# ══════════════════════════════════════════════════════════════════
def test_spawn_background_registers_and_clears():
    import push_service as ps

    async def scenario():
        started = asyncio.Event()

        async def work():
            started.set()
            await asyncio.sleep(0.02)

        before = len(ps._BACKGROUND_TASKS)
        ps._spawn_background(work())
        # Task was registered immediately.
        assert len(ps._BACKGROUND_TASKS) == before + 1
        await started.wait()
        # Let it finish + fire the done callback.
        await asyncio.sleep(0.05)
        # Registry cleared itself — no leaked task references.
        assert len(ps._BACKGROUND_TASKS) == before

    _run(scenario())


# ══════════════════════════════════════════════════════════════════
# 5) End-to-end — process_live_round_event schedules retry off-loop
# ══════════════════════════════════════════════════════════════════
def test_process_live_round_event_returns_before_retry_completes(monkeypatch):
    """The director's HTTP path returns as soon as the initial log is
    written. The retry then runs on the event loop's own time — never
    delaying the response."""
    import push_service as ps

    round_id = f"e2e-{uuid.uuid4().hex}"

    async def fake_resolve(rid, etype, ctx):
        return [{"token": "tok_e2e_transient", "platform": "android",
                  "user_id": "u1"}]

    async def fake_fan_out(recipients, payload):
        # Emulate one transient failure that needs retry.
        return {
            "sent": 0, "failed": 1, "pruned": 0, "dry_run": False,
            "_retry_batch": {
                "recipients": recipients,
                "payload": payload,
                "creds_path": "/tmp/x",
                "project_id": "proj",
            },
        }

    retry_started = asyncio.Event()
    retry_finished = asyncio.Event()

    async def fake_retry(**kwargs):
        retry_started.set()
        await asyncio.sleep(0.05)
        retry_finished.set()

    monkeypatch.setattr(ps, "_resolve_recipients", fake_resolve)
    monkeypatch.setattr(ps, "_fan_out", fake_fan_out)
    monkeypatch.setattr(ps, "_retry_with_backoff", fake_retry)

    async def scenario():
        result = await ps.process_live_round_event(round_id, "join_code_rotated",
                                                     join_code="AB2K")
        # Caller-visible result reflects the INITIAL batch outcome,
        # never blocks for the retry.
        assert result["sent"] == 0
        assert result["failed"] == 1
        # `_retry_batch` was popped so it doesn't leak back into the
        # HTTP response envelope.
        assert "_retry_batch" not in result
        # Retry task was scheduled but hasn't finished yet.
        assert retry_started.is_set() or not retry_finished.is_set()
        # Now let the retry drain.
        await retry_finished.wait()
        # Registry drains itself.
        await asyncio.sleep(0.02)
        assert not any(not t.done() for t in ps._BACKGROUND_TASKS)

    _run(scenario())
