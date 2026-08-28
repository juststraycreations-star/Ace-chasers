"""Iteration 5 tests:

- /api/feed posts now carry `recent_comments` (up to 3 newest, chronological).
- Same field is populated on /api/users/{uid}/posts.
"""
from __future__ import annotations

import os
import sys
import uuid

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


def _signup():
    email = f"TEST_i5_{uuid.uuid4().hex[:8]}@example.com"
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
def author():
    u = _signup()
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def _create_post(author, body="hi"):
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


def test_feed_post_includes_recent_comments_field(author):
    """Newly created post should appear in feed with `recent_comments: []`."""
    post = _create_post(author, body=f"i5 fresh {uuid.uuid4().hex[:6]}")
    r = requests.get(
        f"{BASE_URL}/api/feed", headers=_h(author["id_token"]), timeout=15
    )
    assert r.status_code == 200, r.text
    posts = r.json()["posts"]
    me = next((p for p in posts if p["id"] == post["id"]), None)
    assert me is not None
    assert "recent_comments" in me
    assert me["recent_comments"] == []


def test_feed_post_returns_up_to_3_newest_comments_chronological(author):
    post = _create_post(author, body=f"i5 with comments {uuid.uuid4().hex[:6]}")
    bodies = ["one", "two", "three", "four", "five"]
    for b in bodies:
        _add_comment(author, post["id"], b)
    r = requests.get(
        f"{BASE_URL}/api/feed", headers=_h(author["id_token"]), timeout=15
    )
    assert r.status_code == 200
    posts = r.json()["posts"]
    me = next((p for p in posts if p["id"] == post["id"]), None)
    assert me is not None
    assert me["comment_count"] == 5
    preview = me["recent_comments"]
    assert len(preview) == 3
    # Should be chronological (oldest of the 3 newest first).
    # Five inserts in order -> newest 3 are "three","four","five" -> reversed
    # to chronological gives ["three","four","five"].
    assert [c["body"] for c in preview] == ["three", "four", "five"]
    # Each preview comment carries author + is_mine.
    for c in preview:
        assert c["author"]["uid"] == author["uid"]
        assert c["is_mine"] is True


def test_user_posts_endpoint_also_carries_recent_comments(author):
    post = _create_post(author, body=f"i5 user posts {uuid.uuid4().hex[:6]}")
    _add_comment(author, post["id"], "hello")
    r = requests.get(
        f"{BASE_URL}/api/users/{author['uid']}/posts",
        headers=_h(author["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    rows = r.json()
    target = next((p for p in rows if p["id"] == post["id"]), None)
    assert target is not None
    assert len(target["recent_comments"]) == 1
    assert target["recent_comments"][0]["body"] == "hello"
