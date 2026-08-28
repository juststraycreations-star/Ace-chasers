"""Iteration 71 — Push fan-out worker (dry-run mode).

Because the sandbox has no `FIREBASE_SERVICE_ACCOUNT_PATH`, the sender
falls into dry-run mode (returns `dry_run: True, sent: 0`). We verify:
  1) `process_live_round_event` never raises, even for unknown events.
  2) Recipient resolution for `join_code_rotated` reads every checked-in
     player's user_id → push_token.
  3) Recipient resolution for `payouts_finalized` reads every member in
     the division.
  4) Payload builder emits the exact copy the manager brief specified
     for the payouts alert and a silent data-only payload for the code
     rotation event.

These tests exercise the private helpers directly so they don't need
the OS FCM stack. Runtime FCM verification happens locally against a
real service-account credential file.
"""
from __future__ import annotations
import os
import uuid
import asyncio
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _run(coro): return asyncio.get_event_loop().run_until_complete(coro)


async def _seed(members, scorecards, push_tokens):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    if members:      await db.league_members.insert_many(members)
    if scorecards:   await db.scorecards.insert_many(scorecards)
    if push_tokens:  await db.push_tokens.insert_many(push_tokens)
    client.close()


async def _cleanup(user_ids):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.push_tokens.delete_many({"user_id": {"$in": user_ids}})
    await db.league_members.delete_many({"user_id": {"$in": user_ids}})
    client.close()


def test_process_live_round_event_returns_dry_run_summary():
    from push_service import process_live_round_event  # type: ignore
    # Unknown event type is harmless.
    summary = _run(process_live_round_event("some-round", "does-not-exist"))
    assert isinstance(summary, dict)
    assert summary.get("sent") == 0


def test_join_code_rotated_resolves_checked_in_players():
    """Fan-out for a code rotation must pull only the players who have
    a scorecard on THIS round, then match their user_ids to push_tokens."""
    from push_service import _resolve_recipients  # type: ignore
    league_id = uuid.uuid4().hex
    round_id = uuid.uuid4().hex
    user_ids = [uuid.uuid4().hex for _ in range(3)]
    member_ids = [uuid.uuid4().hex for _ in range(3)]
    members = [
        {"id": member_ids[i], "league_id": league_id,
         "user_id": user_ids[i], "name": f"P{i}", "division": "Open"}
        for i in range(3)
    ]
    # Only 2 players are checked into this round.
    scorecards = [
        {"id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
         "member_id": member_ids[0], "total": 3, "plus_minus": 0, "scores": [3]},
        {"id": uuid.uuid4().hex, "league_id": league_id, "round_id": round_id,
         "member_id": member_ids[1], "total": 4, "plus_minus": 1, "scores": [4]},
    ]
    # Only 2 have push tokens registered.
    push_tokens = [
        {"id": uuid.uuid4().hex, "user_id": user_ids[0],
         "token": f"tok-{uuid.uuid4().hex}", "platform": "android"},
        {"id": uuid.uuid4().hex, "user_id": user_ids[1],
         "token": f"tok-{uuid.uuid4().hex}", "platform": "android"},
    ]
    _run(_seed(members, scorecards, push_tokens))
    try:
        recipients = _run(_resolve_recipients(round_id, "join_code_rotated", {}))
        assert {r["user_id"] for r in recipients} == {user_ids[0], user_ids[1]}
    finally:
        _run(_cleanup(user_ids))


def test_payouts_finalized_resolves_division_members():
    """payouts_finalized narrows to the division named in ctx."""
    from push_service import _resolve_recipients  # type: ignore
    league_id = uuid.uuid4().hex
    round_id = uuid.uuid4().hex
    user_ids = [uuid.uuid4().hex for _ in range(3)]
    member_ids = [uuid.uuid4().hex for _ in range(3)]
    members = [
        {"id": member_ids[0], "league_id": league_id, "user_id": user_ids[0], "division": "MPO", "name": "A"},
        {"id": member_ids[1], "league_id": league_id, "user_id": user_ids[1], "division": "MPO", "name": "B"},
        {"id": member_ids[2], "league_id": league_id, "user_id": user_ids[2], "division": "FA",  "name": "C"},
    ]
    push_tokens = [
        {"id": uuid.uuid4().hex, "user_id": uid,
         "token": f"tok-{uuid.uuid4().hex}", "platform": "android"}
        for uid in user_ids
    ]
    # Seed the round doc so _resolve_recipients can find its league.
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    _run(db.rounds.insert_one({
        "id": round_id, "league_id": league_id, "name": "Payout W",
        "holes": 3, "par_per_hole": [3, 3, 3], "status": "active",
    }))
    client.close()
    _run(_seed(members, [], push_tokens))
    try:
        recipients = _run(_resolve_recipients(
            round_id, "payouts_finalized", {"division": "MPO"}
        ))
        # Only the two MPO players are notified.
        assert {r["user_id"] for r in recipients} == {user_ids[0], user_ids[1]}
    finally:
        _run(_cleanup(user_ids))
        client = AsyncIOMotorClient(MONGO_URL); client[DB_NAME].rounds.delete_one({"id": round_id})


def test_payload_builder_contains_exact_manager_brief_copy():
    from push_service import _build_payload  # type: ignore
    silent = _build_payload("r1", "join_code_rotated",
                              {"join_code": "AB2K", "old_code": "XY7Q"})
    # Silent data-only — no `notification` block.
    assert "notification" not in silent
    assert silent["data"]["type"] == "join_code_rotated"
    assert silent["data"]["join_code"] == "AB2K"
    assert silent["android"]["priority"] == "HIGH"

    alert = _build_payload("r1", "payouts_finalized",
                             {"league_id": "L1", "division": "MPO"})
    # Exact copy the manager brief specified.
    assert alert["notification"]["body"] == (
        "Payouts are live! Check the clubhouse ledger to see your cash breakdown."
    )
    assert alert["android"]["priority"] == "HIGH"
    assert alert["android"]["notification"]["channel_id"] == "ace_chasers_payouts"


def test_process_never_raises_on_missing_round():
    """A payouts_finalized event for a round that doesn't exist must
    return a clean summary, not throw."""
    from push_service import process_live_round_event  # type: ignore
    result = _run(process_live_round_event(
        f"missing-{uuid.uuid4().hex}", "payouts_finalized",
        league_id="nope", division="MPO",
    ))
    assert result.get("sent") == 0
    assert not result.get("error")
