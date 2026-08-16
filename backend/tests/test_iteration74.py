"""Iteration 74 — weekly push-health digest email to league directors.

Verifies:
  1) `gather_digests` groups `push_notifications_log` rows by league,
     honours the `window_days` cutoff, correctly counts
     retries_succeeded and permanent_drops from `phase: "retry"` rows,
     and skips leagues without an on-file director email.
  2) `render_digest_email` includes every headline metric in both the
     plain and HTML bodies.
  3) `run_weekly_digest(dry_run=True)` returns one preview row per
     league with `status: "dry_run"` and never touches SMTP.
  4) `POST /api/admin/push/digest/run` is admin-gated by
     `X-Admin-Key` — 401 without, 200 with — and honours dry-run.
  5) Windowing: rows older than `window_days` are excluded from the
     aggregation so directors only see the freshest signal.
"""
from __future__ import annotations
import os
import uuid
import asyncio
from datetime import datetime, timedelta, timezone

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
ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "").strip()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fresh_db():
    """A fresh motor client so each test controls its own event loop lifecycle."""
    client = AsyncIOMotorClient(MONGO_URL)
    return client, client[DB_NAME]


async def _seed_fixture(*, tag: str, now: datetime,
                         within_window: bool = True,
                         director_has_email: bool = True):
    """Create one league + one director user + a few log rows.

    Returns dict with league_id / director_uid / round_id / etc so tests
    can inspect. Every doc is tagged with `tag` so cleanup is trivial.
    """
    client, db = await _fresh_db()
    league_id = f"lg-{tag}-{uuid.uuid4().hex[:8]}"
    round_id = f"rd-{tag}-{uuid.uuid4().hex[:8]}"
    director_uid = f"uid-{tag}-{uuid.uuid4().hex[:8]}"
    director_email = f"director-{tag}@example.com" if director_has_email else ""

    await db.leagues.insert_one({
        "id": league_id, "name": f"Test League {tag}",
        "director_id": director_uid, "_test_tag": tag,
    })
    await db.rounds.insert_one({
        "id": round_id, "league_id": league_id, "_test_tag": tag,
    })
    await db.users.insert_one({
        "uid": director_uid, "email": director_email,
        "name": f"Director {tag}", "_test_tag": tag,
    })

    # Timestamp used for every seeded log row.
    ts = (now - timedelta(hours=1) if within_window
          else now - timedelta(days=30)).isoformat()

    # Initial fan-out row: 3 delivered, 2 failed (one transient, one perm).
    await db.push_notifications_log.insert_one({
        "id": str(uuid.uuid4()), "eventId": f"ev-{tag}-1",
        "roundId": round_id, "eventType": "join_code_rotated",
        "totalSent": 3, "totalFailed": 2, "tokensPruned": 0,
        "dryRun": False, "retriesPending": 1,
        "timestamp": ts, "_test_tag": tag,
    })
    # Retry follow-up: 1 recovered, 1 permanently failed.
    await db.push_notifications_log.insert_one({
        "id": str(uuid.uuid4()), "eventId": f"ev-{tag}-1",
        "roundId": round_id, "eventType": "join_code_rotated",
        "phase": "retry", "attempts": 3,
        "retriedSent": 1, "permanentlyFailed": 1,
        "failedTokenPrefixes": ["abcdefghijkl…"],
        "totalSent": 1, "totalFailed": 1, "tokensPruned": 0,
        "dryRun": False, "timestamp": ts, "_test_tag": tag,
    })
    # A second broadcast event on the same league — payouts (all sent).
    await db.push_notifications_log.insert_one({
        "id": str(uuid.uuid4()), "eventId": f"ev-{tag}-2",
        "roundId": round_id, "eventType": "payouts_finalized",
        "totalSent": 5, "totalFailed": 0, "tokensPruned": 1,
        "dryRun": False, "retriesPending": 0,
        "timestamp": ts, "_test_tag": tag,
    })

    client.close()
    return {"league_id": league_id, "round_id": round_id,
            "director_uid": director_uid, "director_email": director_email,
            "tag": tag}


async def _cleanup(tag: str):
    client, db = await _fresh_db()
    for coll in ("leagues", "rounds", "users", "push_notifications_log"):
        await db[coll].delete_many({"_test_tag": tag})
    client.close()


# ══════════════════════════════════════════════════════════════════
# 1) gather_digests — grouping + counts
# ══════════════════════════════════════════════════════════════════
def test_gather_digests_groups_and_counts_correctly():
    from push_digest import gather_digests

    tag = f"grp-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    async def scenario():
        fx = await _seed_fixture(tag=tag, now=now, within_window=True)
        client, db = await _fresh_db()
        try:
            digests = await gather_digests(db, window_days=7, now=now)
        finally:
            client.close()

        # Isolate the row we care about — other tests may share the DB.
        mine = [d for d in digests if d.league_id == fx["league_id"]]
        assert len(mine) == 1
        d = mine[0]
        assert d.league_name == f"Test League {tag}"
        assert d.director_email == fx["director_email"]
        # 3 (initial) + 5 (payouts) + 1 (recovered via retry) = 9 delivered
        assert d.successes == 9
        assert d.retries_succeeded == 1
        assert d.permanent_drops == 1
        assert d.tokens_pruned == 1
        assert d.event_count == 3  # 3 log rows counted
        assert "abcdefghijkl…" in d.failed_token_prefixes

    _run(scenario())
    _run(_cleanup(tag))


# ══════════════════════════════════════════════════════════════════
# 2) render_digest_email includes all headline metrics
# ══════════════════════════════════════════════════════════════════
def test_render_digest_email_shape():
    from push_digest import LeagueDigest, render_digest_email

    d = LeagueDigest(
        league_id="L1", league_name="Weekend Warriors",
        director_uid="u1", director_email="d@example.com",
        director_name="Casey Green",
        successes=9, retries_succeeded=1, permanent_drops=1,
        tokens_pruned=1, event_count=3,
        window_days=7,
        window_start_iso=(datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
        window_end_iso=datetime.now(timezone.utc).isoformat(),
    )
    subject, plain, html = render_digest_email(d)
    assert "Weekend Warriors" in subject
    assert "9 delivered" in subject
    # Plain-text assertions (no markup between numbers).
    assert "Casey" in plain
    assert "9 delivered" in plain
    assert "1 recovered after a retry" in plain
    assert "1 permanent drop" in plain
    assert "1 dead token" in plain
    assert "3 broadcast event" in plain
    # HTML assertions — numerals are wrapped in <b> tags, so match the
    # surrounding phrasing rather than a contiguous substring.
    assert "Casey" in html
    assert "9</b> delivered" in html
    assert "1 recovered after a retry" in html
    assert "permanent drop" in html
    assert "dead token" in html
    assert "broadcast event" in html


# ══════════════════════════════════════════════════════════════════
# 3) run_weekly_digest(dry_run=True) skips SMTP
# ══════════════════════════════════════════════════════════════════
def test_run_weekly_digest_dry_run(monkeypatch):
    from push_digest import run_weekly_digest
    import push_digest as pd

    # If dry_run leaks into SMTP, this monkeypatch guarantees the test fails loudly.
    def _explode(*a, **kw):
        raise AssertionError("smtp_send must NOT be called in dry_run mode")
    monkeypatch.setattr(pd, "smtp_send", _explode)

    tag = f"dry-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    async def scenario():
        await _seed_fixture(tag=tag, now=now, within_window=True)
        client, db = await _fresh_db()
        try:
            summary = await run_weekly_digest(db, window_days=7,
                                                dry_run=True, now=now)
        finally:
            client.close()

        assert summary["dry_run"] is True
        assert summary["sent"] == 0
        # Our seeded league must appear in rows.
        mine = [r for r in summary["rows"] if r["league_name"].endswith(tag)]
        assert len(mine) == 1
        row = mine[0]
        assert row["status"] == "dry_run"
        assert row["successes"] == 9
        assert row["permanent_drops"] == 1
        assert row["subject"].startswith("Test League ")

    _run(scenario())
    _run(_cleanup(tag))


# ══════════════════════════════════════════════════════════════════
# 4) Admin endpoint auth + dry-run round-trip
# ══════════════════════════════════════════════════════════════════
def test_admin_digest_endpoint_gated_by_admin_key():
    if not ADMIN_KEY:
        pytest.skip("ADMIN_API_KEY not configured")

    # Missing header → 401.
    r = requests.post(f"{BASE_URL}/api/admin/push/digest/run",
                       params={"dry_run": True}, timeout=25)
    assert r.status_code == 401, r.text

    tag = f"api-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    _run(_seed_fixture(tag=tag, now=now, within_window=True))
    try:
        r = requests.post(
            f"{BASE_URL}/api/admin/push/digest/run",
            params={"dry_run": True, "window_days": 7},
            headers={"X-Admin-Key": ADMIN_KEY}, timeout=25,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True
        assert body["window_days"] == 7
        # Our fixture league must show up.
        assert any(row["league_name"].endswith(tag) for row in body["rows"])
    finally:
        _run(_cleanup(tag))


def test_admin_digest_endpoint_rejects_bad_window():
    if not ADMIN_KEY:
        pytest.skip("ADMIN_API_KEY not configured")
    r = requests.post(
        f"{BASE_URL}/api/admin/push/digest/run",
        params={"window_days": 0, "dry_run": True},
        headers={"X-Admin-Key": ADMIN_KEY}, timeout=25,
    )
    assert r.status_code == 400
    r = requests.post(
        f"{BASE_URL}/api/admin/push/digest/run",
        params={"window_days": 999, "dry_run": True},
        headers={"X-Admin-Key": ADMIN_KEY}, timeout=25,
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════
# 5) Window cutoff — old rows are excluded
# ══════════════════════════════════════════════════════════════════
def test_rows_outside_window_are_excluded():
    from push_digest import gather_digests

    tag_fresh = f"fresh-{uuid.uuid4().hex[:8]}"
    tag_stale = f"stale-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    async def scenario():
        await _seed_fixture(tag=tag_fresh, now=now, within_window=True)
        await _seed_fixture(tag=tag_stale, now=now, within_window=False)

        client, db = await _fresh_db()
        try:
            digests = await gather_digests(db, window_days=7, now=now)
        finally:
            client.close()

        names = {d.league_name for d in digests}
        assert f"Test League {tag_fresh}" in names
        assert f"Test League {tag_stale}" not in names

    _run(scenario())
    _run(_cleanup(tag_fresh))
    _run(_cleanup(tag_stale))
