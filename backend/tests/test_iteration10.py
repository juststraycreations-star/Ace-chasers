"""Iteration 10 tests:

- Seed/demo users are filtered out of /api/discovery, /api/inbox, /api/likes,
  /api/friends (real users only across the app).
- POST /api/posts/{post_id}/comments/{comment_id}/nice toggles a Nice on a
  single comment; counts + liked_by_me reflect correctly. /api/feed and
  /api/posts/{post_id}/comments now carry nice_count + liked_by_me on every
  comment.
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


def _signup(prefix="i10"):
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
def alice():
    u = _signup("i10a")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def bob():
    u = _signup("i10b")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def seed_user():
    """Insert a fake seed user directly via Mongo so we can assert it's
    excluded from public-facing endpoints. Yields the uid + cleans up."""
    import asyncio
    from db import get_db

    uid = f"seed-i10-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()

    async def setup():
        db = get_db()
        await db.users.insert_one(
            {
                "uid": uid,
                "email": f"{uid}@demo.local",
                "name": "I10 Seed",
                "is_seed": True,
                "created_at": now,
            }
        )

    async def teardown():
        db = get_db()
        await db.users.delete_one({"uid": uid})
        await db.swipes.delete_many({"$or": [{"from_uid": uid}, {"to_uid": uid}]})

    asyncio.get_event_loop().run_until_complete(setup())
    yield uid
    asyncio.get_event_loop().run_until_complete(teardown())


def test_discovery_excludes_seed_users(alice, seed_user):
    r = requests.get(
        f"{BASE_URL}/api/discovery", headers=_h(alice["id_token"]), timeout=15
    )
    assert r.status_code == 200
    uids = [p["uid"] for p in r.json()["players"]]
    assert seed_user not in uids, "Seed users must never appear in Discovery"


def test_inbox_excludes_seed_likes(alice, seed_user):
    """If a seed user had pre-liked a real user (legacy DB rows), the inbox
    should not surface them."""
    import asyncio
    from db import get_db

    async def insert_seed_swipe():
        db = get_db()
        await db.swipes.update_one(
            {"from_uid": seed_user, "to_uid": alice["uid"]},
            {
                "$set": {
                    "from_uid": seed_user,
                    "to_uid": alice["uid"],
                    "action": "like",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )

    asyncio.get_event_loop().run_until_complete(insert_seed_swipe())

    r = requests.get(f"{BASE_URL}/api/inbox", headers=_h(alice["id_token"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    like_uids = [il["from_user"]["uid"] for il in body.get("incoming_likes", [])]
    assert seed_user not in like_uids


# --- Comment nice ---------------------------------------------------------

def _create_post(author, body):
    r = requests.post(
        f"{BASE_URL}/api/posts",
        headers=_h(author["id_token"]),
        files={"body": (None, body), "visibility": (None, "public")},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _add_comment(user, post_id, body):
    r = requests.post(
        f"{BASE_URL}/api/posts/{post_id}/comments",
        headers=_h(user["id_token"]),
        json={"body": body},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_comment_nice_toggle_round_trip(alice, bob):
    post = _create_post(alice, f"i10 comment-nice {uuid.uuid4().hex[:6]}")
    comment = _add_comment(alice, post["id"], "hello world")

    # Bob toggles Nice on Alice's comment.
    r = requests.post(
        f"{BASE_URL}/api/posts/{post['id']}/comments/{comment['id']}/nice",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nice_count"] == 1
    assert body["liked_by_me"] is True

    # Same user tapping again removes it (toggle off).
    r = requests.post(
        f"{BASE_URL}/api/posts/{post['id']}/comments/{comment['id']}/nice",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nice_count"] == 0
    assert body["liked_by_me"] is False


def test_feed_carries_comment_reactions(alice, bob):
    post = _create_post(alice, f"i10 feed-reactions {uuid.uuid4().hex[:6]}")
    comment = _add_comment(alice, post["id"], "react to me")
    # Bob likes the comment.
    requests.post(
        f"{BASE_URL}/api/posts/{post['id']}/comments/{comment['id']}/nice",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    # Bob fetches feed and sees nice_count=1 + liked_by_me=true on that comment.
    r = requests.get(f"{BASE_URL}/api/feed", headers=_h(bob["id_token"]), timeout=15)
    assert r.status_code == 200
    posts = r.json()["posts"]
    target = next((p for p in posts if p["id"] == post["id"]), None)
    assert target is not None
    preview = [c for c in target["recent_comments"] if c["id"] == comment["id"]]
    assert preview, "newly-niced comment should appear in recent_comments"
    assert preview[0]["nice_count"] == 1
    assert preview[0]["liked_by_me"] is True

    # Alice (author) sees the same count but liked_by_me=False (she didn't tap).
    r2 = requests.get(f"{BASE_URL}/api/feed", headers=_h(alice["id_token"]), timeout=15)
    posts2 = r2.json()["posts"]
    target2 = next((p for p in posts2 if p["id"] == post["id"]), None)
    preview2 = [c for c in target2["recent_comments"] if c["id"] == comment["id"]]
    assert preview2[0]["nice_count"] == 1
    assert preview2[0]["liked_by_me"] is False


def test_list_comments_carries_reactions(alice, bob):
    post = _create_post(alice, f"i10 list-reactions {uuid.uuid4().hex[:6]}")
    comment = _add_comment(alice, post["id"], "list me")
    requests.post(
        f"{BASE_URL}/api/posts/{post['id']}/comments/{comment['id']}/nice",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    r = requests.get(
        f"{BASE_URL}/api/posts/{post['id']}/comments",
        headers=_h(bob["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    rows = r.json()
    row = next((c for c in rows if c["id"] == comment["id"]), None)
    assert row is not None
    assert row["nice_count"] == 1
    assert row["liked_by_me"] is True
