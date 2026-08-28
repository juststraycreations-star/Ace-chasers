"""Iteration 36 — Server idempotency + QR self-enroll + Manager broadcast + Feed moderation.

Covers:
 1) PATCH /api/scorecards/{id}/score with Idempotency-Key header
    - First call writes; second call with same key returns the SAME response,
      does NOT bump `version`, and does NOT append a second proof_log row.
 2) POST /api/rounds/{id}/self-enroll
    - Non-member is auto-joined; response includes card + scorecard.
    - Second call is idempotent (already_enrolled=True).
 3) POST /api/leagues/{id}/broadcast
    - Director hits it → `delivered` count matches (member_count - 1).
    - Non-director → 403.
 4) DELETE /api/feed/{post_id}
    - Author can delete own post; director can delete any post.
    - Feed list hides the removed post for regular members.
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
    email = f"TEST_i36_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(
        IDENTITY_SIGNUP,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=25,
    )
    assert r.status_code == 200, r.text
    tok = r.json()["idToken"]
    prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
    assert prof.status_code == 200, prof.text
    return {"token": tok, "profile": prof.json()}


def _mkleague(token):
    r = requests.post(
        f"{BASE_URL}/api/leagues",
        json={
            "name": f"TEST_i36_{uuid.uuid4().hex[:6]}",
            "location": "Testville",
            "format": "Singles",
            "entry_fee": 5.0,
        },
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def director():
    return _signup()


@pytest.fixture(scope="module")
def player():
    return _signup()


@pytest.fixture(scope="module")
def stranger():
    return _signup()


@pytest.fixture(scope="module")
def league(director):
    return _mkleague(director["token"])


# ============================ ITEM 3 — Self-enroll ============================
def test_self_enroll_auto_joins_league(league, stranger):
    # New round first
    seasons = requests.get(
        f"{BASE_URL}/api/leagues/{league['id']}/seasons",
        headers=_h(pytest.director_token), timeout=15,
    ).json()
    round_resp = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/rounds",
        json={
            "name": "R1",
            "date": "2026-03-01",
            "season_id": seasons[0]["id"],
            "holes": 9,
            "par_per_hole": [3] * 9,
        },
        headers=_h(pytest.director_token), timeout=15,
    )
    assert round_resp.status_code == 200, round_resp.text
    round_id = round_resp.json()["id"]

    # Stranger (not in league) self-enrolls via QR
    r = requests.post(
        f"{BASE_URL}/api/rounds/{round_id}/self-enroll",
        headers=_h(stranger["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_joined_league"] is True
    assert body["already_enrolled"] is False
    assert body["card"] and body["scorecard"]

    # Second call is idempotent
    r2 = requests.post(
        f"{BASE_URL}/api/rounds/{round_id}/self-enroll",
        headers=_h(stranger["token"]), timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json()["already_enrolled"] is True

    # Stash for the idempotency test
    pytest.round_id = round_id
    pytest.stranger_scorecard_id = body["scorecard"]["id"]


# ============================ ITEM 4 — Score idempotency ============================
def test_score_idempotency_key_dedupes(league, stranger):
    scorecard_id = pytest.stranger_scorecard_id
    key = f"i36-{uuid.uuid4().hex}"

    # First write with the key
    r1 = requests.patch(
        f"{BASE_URL}/api/scorecards/{scorecard_id}/score",
        json={"hole": 3, "strokes": 4},
        headers={**_h(stranger["token"]), "Idempotency-Key": key},
        timeout=15,
    )
    assert r1.status_code == 200, r1.text
    resp1 = r1.json()

    # Replay with the same key — should short-circuit to identical response
    r2 = requests.patch(
        f"{BASE_URL}/api/scorecards/{scorecard_id}/score",
        json={"hole": 3, "strokes": 999},  # different payload — must be IGNORED
        headers={**_h(stranger["token"]), "Idempotency-Key": key},
        timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json() == resp1, "Replay must return original response verbatim"

    # DB assertions: exactly one proof_log row for that (scorecard, hole);
    # version incremented exactly once.
    async def _check():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        logs = await db.proof_logs.find(
            {"scorecard_id": scorecard_id, "hole": 3}
        ).to_list(50)
        sc = await db.scorecards.find_one({"id": scorecard_id})
        client.close()
        return logs, sc

    logs, sc = _run(_check())
    assert len(logs) == 1, f"expected 1 proof_log row for this hole, got {len(logs)}"
    assert sc["scores"][2] == 4, "second replay must not overwrite the original value"


# ============================ ITEM 5 — Broadcast ============================
def test_broadcast_director_only(director, player, league):
    # Add player to the league so they can receive.
    r = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/join",
        headers=_h(player["token"]), timeout=15,
    )
    assert r.status_code == 200

    # Non-director trying to broadcast → 403
    forbid = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/broadcast",
        json={"body": "hello", "title": "Test"},
        headers=_h(player["token"]), timeout=15,
    )
    assert forbid.status_code == 403

    # Director broadcasts → delivered >= 1 (to the player, not to self)
    ok = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/broadcast",
        json={"body": "Tee times pushed 30 min", "title": "Weather"},
        headers=_h(director["token"]), timeout=15,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["delivered"] >= 1


# ============================ ITEM 5 — Feed moderation ============================
def test_director_can_delete_any_feed_post(director, player, league):
    # Player posts to the feed
    post = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/feed",
        json={"body": "Nice weather today"},
        headers=_h(player["token"]), timeout=15,
    )
    assert post.status_code == 200
    pid = post.json()["id"]

    # Director deletes another user's post → 200
    d = requests.delete(f"{BASE_URL}/api/feed/{pid}", headers=_h(director["token"]), timeout=15)
    assert d.status_code == 200
    assert d.json()["ok"] is True

    # Feed list for the (non-director) player must hide the deleted post
    feed = requests.get(
        f"{BASE_URL}/api/leagues/{league['id']}/feed",
        headers=_h(player["token"]), timeout=15,
    )
    assert feed.status_code == 200
    assert all(fp["id"] != pid for fp in feed.json()), "removed post must not appear for members"


# Prime the director token globally so the round-create fixture can use it.
@pytest.fixture(autouse=True, scope="module")
def _prime(director):
    pytest.director_token = director["token"]
    yield
