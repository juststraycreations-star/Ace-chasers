"""Iteration 19 tests: deployment-readiness perf refactor verification.

The PostOut contract must be unchanged after _hydrate_post was converted
from N+1 to a batched _hydrate_posts helper. Also verifies the projection
fixes on /api/likes and /api/users/{uid}/friends.
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


# --- helpers ---------------------------------------------------------------


def _signup(prefix="i19"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _sync(u, name=None):
    payload = {}
    if name:
        payload["name"] = name
    r = requests.post(
        f"{BASE_URL}/api/auth/sync", json=payload, headers=_h(u["id_token"]), timeout=20
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def user():
    u = _signup("user")
    _sync(u, name=f"Iter19 User {u['uid'][:6]}")
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def viewer():
    u = _signup("viewer")
    _sync(u, name=f"Iter19 Viewer {u['uid'][:6]}")
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


# --- expected PostOut shape ------------------------------------------------

EXPECTED_POST_FIELDS = {
    "id",
    "body",
    "author",
    "nice_count",
    "down_count",
    "liked_by_me",
    "disliked_by_me",
    "comment_count",
    "is_mine",
    "recent_comments",
    "image_url",
    "video_url",
    "visibility",
    "kind",
    "created_at",
}


def _assert_post_shape(post: dict):
    missing = EXPECTED_POST_FIELDS - set(post.keys())
    assert not missing, f"PostOut missing fields: {missing}; got keys={list(post.keys())}"
    assert isinstance(post["author"], dict), "author must be an object"
    for k in ("uid", "name", "profilePictureUrl"):
        assert k in post["author"], f"author missing {k}"


# --- tests -----------------------------------------------------------------

# Feed on a fresh user must return an empty posts array but valid envelope.
class TestEmptyFeed:
    def test_empty_feed(self, viewer):
        r = requests.get(f"{BASE_URL}/api/feed", headers=_h(viewer["id_token"]), timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "posts" in d and isinstance(d["posts"], list)
        assert "next_cursor" in d


# POST /api/posts and verify the hydrated PostOut contract.
class TestCreatePostHydration:
    def test_create_post_returns_hydrated_postout(self, user):
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "hello world", "visibility": "public", "kind": "post"},
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        post = r.json()
        _assert_post_shape(post)
        assert post["body"] == "hello world"
        assert post["nice_count"] == 0
        assert post["down_count"] == 0
        assert post["comment_count"] == 0
        assert post["liked_by_me"] is False
        assert post["disliked_by_me"] is False
        assert post["is_mine"] is True
        assert post["author"]["uid"] == user["uid"]
        # Stash for later tests
        TestCreatePostHydration.post_id = post["id"]

    def test_feed_includes_created_post(self, user):
        r = requests.get(f"{BASE_URL}/api/feed", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200, r.text
        posts = r.json()["posts"]
        ids = [p["id"] for p in posts]
        assert TestCreatePostHydration.post_id in ids
        post = next(p for p in posts if p["id"] == TestCreatePostHydration.post_id)
        _assert_post_shape(post)
        assert post["author"]["uid"] == user["uid"]
        # batched author lookup must include name field in payload (value
        # may be None if Firebase signup didn't supply a display name).
        assert "name" in post["author"]


# Toggle Nice and verify batched my_reactions lookup reflects state on feed.
class TestNiceToggleBatched:
    def test_nice_then_feed_shows_liked(self, user):
        pid = TestCreatePostHydration.post_id
        r = requests.post(
            f"{BASE_URL}/api/posts/{pid}/nice", headers=_h(user["id_token"]), timeout=20
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nice_count"] == 1
        assert d["liked_by_me"] is True

        # Refetch feed — batched my_reactions must pick this up.
        r2 = requests.get(f"{BASE_URL}/api/feed", headers=_h(user["id_token"]), timeout=20)
        assert r2.status_code == 200
        post = next(p for p in r2.json()["posts"] if p["id"] == pid)
        assert post["nice_count"] == 1, f"feed nice_count mismatch: {post}"
        assert post["liked_by_me"] is True, f"feed liked_by_me wrong: {post}"
        assert post["disliked_by_me"] is False

    def test_nice_toggle_off(self, user):
        pid = TestCreatePostHydration.post_id
        r = requests.post(
            f"{BASE_URL}/api/posts/{pid}/nice", headers=_h(user["id_token"]), timeout=20
        )
        assert r.status_code == 200
        d = r.json()
        assert d["nice_count"] == 0
        assert d["liked_by_me"] is False

        r2 = requests.get(f"{BASE_URL}/api/feed", headers=_h(user["id_token"]), timeout=20)
        post = next(p for p in r2.json()["posts"] if p["id"] == pid)
        assert post["nice_count"] == 0
        assert post["liked_by_me"] is False


# Comment then feed must reflect batched comment_count + recent_comments.
class TestCommentBatched:
    def test_comment_then_feed(self, user):
        pid = TestCreatePostHydration.post_id
        r = requests.post(
            f"{BASE_URL}/api/posts/{pid}/comments",
            json={"body": "nice shot"},
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["body"] == "nice shot"

        r2 = requests.get(f"{BASE_URL}/api/feed", headers=_h(user["id_token"]), timeout=20)
        post = next(p for p in r2.json()["posts"] if p["id"] == pid)
        assert post["comment_count"] == 1, f"comment_count mismatch: {post}"
        bodies = [rc["body"] for rc in post.get("recent_comments", [])]
        assert "nice shot" in bodies, f"recent_comments missing new comment: {bodies}"


# Profile page posts must use same batched helper as feed.
class TestUserPostsBatched:
    def test_user_posts_endpoint(self, user):
        r = requests.get(
            f"{BASE_URL}/api/users/{user['uid']}/posts",
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        posts = r.json()
        assert isinstance(posts, list)
        assert len(posts) >= 1
        for p in posts:
            _assert_post_shape(p)
            assert p["author"]["uid"] == user["uid"]
            assert p["is_mine"] is True


# Validates projection fix on social_router.py:351 (my_likes_cursor).
class TestLikesProjection:
    def test_likes_endpoint(self, user):
        r = requests.get(f"{BASE_URL}/api/likes", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# Validates projection fix on social_router.py:169 (_friends_for matches query).
class TestFriendsProjection:
    def test_friends_endpoint(self, user):
        r = requests.get(
            f"{BASE_URL}/api/users/{user['uid']}/friends",
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_my_friends_endpoint(self, user):
        r = requests.get(f"{BASE_URL}/api/friends", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# Mobile feed multipart regression: post 'hi' with multipart boundary set
# by `requests` itself (no explicit Content-Type header).
class TestMobileMultipartRegression:
    def test_post_hi_multipart(self, user):
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "hi", "visibility": "public", "kind": "post"},
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        post = r.json()
        assert post["body"] == "hi"
        _assert_post_shape(post)


# Multi-post batched feed: create several posts, confirm fields populated per-post.
class TestMultiPostFeed:
    def test_multi_post_batch(self, user, viewer):
        # Create a few extra posts as `user`
        created_ids = []
        for i in range(3):
            r = requests.post(
                f"{BASE_URL}/api/posts",
                data={"body": f"batch post {i}", "visibility": "public", "kind": "post"},
                headers=_h(user["id_token"]),
                timeout=20,
            )
            assert r.status_code == 200, r.text
            created_ids.append(r.json()["id"])

        # `user` nicely reacts to one of them so we can assert per-post state.
        target = created_ids[1]
        r = requests.post(
            f"{BASE_URL}/api/posts/{target}/nice",
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200

        # Viewer fetches feed — should see user's public posts.
        r = requests.get(f"{BASE_URL}/api/feed", headers=_h(viewer["id_token"]), timeout=20)
        assert r.status_code == 200
        posts = {p["id"]: p for p in r.json()["posts"]}

        for pid in created_ids:
            assert pid in posts, f"post {pid} missing from viewer feed"
            p = posts[pid]
            _assert_post_shape(p)
            # Viewer hasn't liked anything
            assert p["liked_by_me"] is False
            assert p["disliked_by_me"] is False
            assert p["is_mine"] is False
            assert p["author"]["uid"] == user["uid"]

        # The target post must reflect author's nice in the count
        assert posts[target]["nice_count"] == 1, posts[target]
