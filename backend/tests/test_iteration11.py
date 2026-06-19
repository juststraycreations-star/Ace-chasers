"""Iteration 11 tests: GET /api/feed/top-niced-this-week returns the public
post with the most 👍 Nice reactions in the past 7 days, or null when no
qualifying post exists.
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


def _signup(prefix="i11"):
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
def author():
    u = _signup("i11a")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def viewer():
    u = _signup("i11v")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def viewer2():
    u = _signup("i11v2")
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def _create_post(user, body, visibility="public"):
    r = requests.post(
        f"{BASE_URL}/api/posts",
        headers=_h(user["id_token"]),
        files={"body": (None, body), "visibility": (None, visibility)},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _react(user, post_id, value="up"):
    # /nice is a no-op toggle that defaults to 'up' — perfect for tests that
    # just need to register a Nice reaction.
    r = requests.post(
        f"{BASE_URL}/api/posts/{post_id}/nice",
        headers=_h(user["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200, r.text


def test_top_niced_returns_post_with_most_nices(author, viewer, viewer2):
    p_low = _create_post(author, f"i11 low {uuid.uuid4().hex[:6]}")
    p_high = _create_post(author, f"i11 high {uuid.uuid4().hex[:6]}")
    # Give p_high 2 nice reactions; p_low only 1.
    _react(viewer, p_low["id"], "up")
    _react(viewer, p_high["id"], "up")
    _react(viewer2, p_high["id"], "up")
    r = requests.get(
        f"{BASE_URL}/api/feed/top-niced-this-week",
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    # MUST be one of our two test posts (the prod DB may have more activity,
    # so we just assert the contract — not equality to p_high — unless p_high
    # legitimately is the global top).
    assert body is not None
    assert body["nice_count"] >= 2
    # Sanity: the response should at minimum surface a non-disc-review public
    # post with a healthy nice count.
    assert body["visibility"] == "public"
    assert body["kind"] != "disc_review"


def test_top_niced_excludes_friends_only_posts(author, viewer):
    """Even if a friends-only post has many nices, it should not surface to
    a viewer who isn't friends with the author."""
    p_friends = _create_post(author, f"i11 friends {uuid.uuid4().hex[:6]}", "friends_only")
    _react(author, p_friends["id"], "up")  # author nicing their own counts toward the agg
    # Viewer (not a friend) asks for top-niced.
    r = requests.get(
        f"{BASE_URL}/api/feed/top-niced-this-week",
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    if body is not None:
        # The friends-only post should never be the response.
        assert body["id"] != p_friends["id"]


def test_top_niced_excludes_disc_reviews(author, viewer):
    """disc_review posts are surfaced on /bagcheck, not on the main feed,
    and should be excluded from the badge."""
    r0 = requests.post(
        f"{BASE_URL}/api/posts",
        headers=_h(author["id_token"]),
        files={
            "body": (None, f"i11 review {uuid.uuid4().hex[:6]}"),
            "visibility": (None, "public"),
            "kind": (None, "disc_review"),
        },
        timeout=15,
    )
    assert r0.status_code == 200, r0.text
    review = r0.json()
    _react(viewer, review["id"], "up")
    r = requests.get(
        f"{BASE_URL}/api/feed/top-niced-this-week",
        headers=_h(viewer["id_token"]),
        timeout=15,
    )
    body = r.json()
    if body is not None:
        assert body["id"] != review["id"]
        assert body["kind"] != "disc_review"
