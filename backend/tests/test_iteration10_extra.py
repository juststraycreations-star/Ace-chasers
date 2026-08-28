"""Iteration 10 — extra coverage:

- /api/likes filters out is_seed=true users (legacy mutual-like rows must not
  surface demo accounts).
- /api/friends filters out is_seed=true users.
- POST /api/auth/sync no longer auto-appends seed auto-likes to a brand-new
  user's inbox (verified by signing up a fresh user and asserting the inbox is
  empty of seed-* uids).
- POST /api/posts/{post_id}/comments/{comment_id}/nice returns 404 for a
  non-existent comment id.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _signup(prefix="i10x"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _sync(u):
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=15)
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def fresh_user():
    u = _signup("i10x")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def seed_user_with_mutual(fresh_user):
    """Insert a seed user + a mutual swipe pair so /api/likes and /api/friends
    would surface them if filtering broke."""
    import asyncio
    from db import get_db

    uid = f"seed-i10x-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()

    async def setup():
        db = get_db()
        await db.users.insert_one(
            {
                "uid": uid,
                "email": f"{uid}@demo.acechasers.app",
                "name": "Seed Mutual",
                "is_seed": True,
                "created_at": now,
            }
        )
        # mutual likes
        await db.swipes.update_one(
            {"from_uid": uid, "to_uid": fresh_user["uid"]},
            {"$set": {"from_uid": uid, "to_uid": fresh_user["uid"], "action": "like", "created_at": now}},
            upsert=True,
        )
        await db.swipes.update_one(
            {"from_uid": fresh_user["uid"], "to_uid": uid},
            {"$set": {"from_uid": fresh_user["uid"], "to_uid": uid, "action": "like", "created_at": now}},
            upsert=True,
        )
        # friendship row as well, in case /api/friends reads a separate collection
        await db.friends.update_one(
            {"a_uid": uid, "b_uid": fresh_user["uid"]},
            {"$set": {"a_uid": uid, "b_uid": fresh_user["uid"], "created_at": now}},
            upsert=True,
        )

    async def teardown():
        db = get_db()
        await db.users.delete_one({"uid": uid})
        await db.swipes.delete_many({"$or": [{"from_uid": uid}, {"to_uid": uid}]})
        await db.friends.delete_many({"$or": [{"a_uid": uid}, {"b_uid": uid}]})

    asyncio.get_event_loop().run_until_complete(setup())
    yield uid
    asyncio.get_event_loop().run_until_complete(teardown())


def test_likes_excludes_seed_users(fresh_user, seed_user_with_mutual):
    r = requests.get(f"{BASE_URL}/api/likes", headers=_h(fresh_user["id_token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # Body shape may be {mutual_likes:[...]} or {likes:[...]} — flatten any list of users
    flat_uids = []
    if isinstance(body, dict):
        for v in body.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        flat_uids.append(item.get("uid") or item.get("user", {}).get("uid"))
    elif isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                flat_uids.append(item.get("uid") or item.get("user", {}).get("uid"))
    assert seed_user_with_mutual not in flat_uids, f"Seed user leaked into /api/likes: {body}"


def test_friends_excludes_seed_users(fresh_user, seed_user_with_mutual):
    r = requests.get(f"{BASE_URL}/api/friends", headers=_h(fresh_user["id_token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    flat_uids = []
    if isinstance(body, dict):
        for v in body.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        flat_uids.append(item.get("uid") or item.get("user", {}).get("uid"))
    elif isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                flat_uids.append(item.get("uid") or item.get("user", {}).get("uid"))
    assert seed_user_with_mutual not in flat_uids, f"Seed user leaked into /api/friends: {body}"


def test_auth_sync_does_not_seed_inbound_likes():
    """A brand-new signup who calls /api/auth/sync should have zero seed-* uids
    in their inbox.incoming_likes (the ensure_inbound_likes_for call was
    removed)."""
    u = _signup("i10sync")
    try:
        _sync(u)
        r = requests.get(f"{BASE_URL}/api/inbox", headers=_h(u["id_token"]), timeout=15)
        assert r.status_code == 200
        like_uids = [il["from_user"]["uid"] for il in r.json().get("incoming_likes", [])]
        seed_like_uids = [x for x in like_uids if x.startswith("seed-")]
        assert seed_like_uids == [], f"auth/sync should not auto-add seed likes; got {seed_like_uids}"
    finally:
        try:
            requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
        except Exception:
            pass


def test_comment_nice_returns_404_for_missing_comment(fresh_user):
    # Create a real post but use a junk comment id
    r = requests.post(
        f"{BASE_URL}/api/posts",
        headers=_h(fresh_user["id_token"]),
        files={"body": (None, "post for 404 nice test"), "visibility": (None, "public")},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    post_id = r.json()["id"]
    fake_comment_id = "does-not-exist-" + uuid.uuid4().hex
    r = requests.post(
        f"{BASE_URL}/api/posts/{post_id}/comments/{fake_comment_id}/nice",
        headers=_h(fresh_user["id_token"]),
        timeout=15,
    )
    assert r.status_code == 404, f"expected 404 for missing comment, got {r.status_code} {r.text}"
