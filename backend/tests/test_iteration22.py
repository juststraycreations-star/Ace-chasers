"""Iteration 22 tests: video codec rewrite + PATCH /api/posts/{id} edit.

Covers:
- cloud_storage.browser_compatible_video_url helper (unit)
- GET /api/feed rewrites Cloudinary video_url with f_mp4,vc_h264
- POST /api/posts + GET /api/feed video_url pass-through for /api/uploads/ (unchanged)
- PATCH /api/posts/{id} owner happy path (200, body updated, edited_at set)
- PATCH by non-owner -> 404
- PATCH empty body -> 422
- PATCH nonexistent -> 404
- Freshly created post has edited_at=null
- DELETE still works (regression)
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

# Import backend helper for direct unit test
sys.path.insert(0, "/app/backend")
from cloud_storage import browser_compatible_video_url  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE_ACCT = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _signup(prefix="i22"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _sync(u, name=None):
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=20)
    assert r.status_code == 200, r.text
    if name:
        r2 = requests.put(
            f"{BASE_URL}/api/users/me",
            json={"name": name},
            headers=_h(u["id_token"]),
            timeout=20,
        )
        assert r2.status_code == 200, r2.text


@pytest.fixture(scope="module")
def user_a():
    u = _signup("a")
    _sync(u, name=f"Alice {u['uid'][:6]}")
    yield u
    try:
        requests.post(DELETE_ACCT, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def user_b():
    u = _signup("b")
    _sync(u, name=f"Bob {u['uid'][:6]}")
    yield u
    try:
        requests.post(DELETE_ACCT, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


# --- 1. Unit: browser_compatible_video_url --------------------------------

class TestBrowserCompatibleVideoUrlHelper:
    def test_non_cloudinary_url_unchanged(self):
        u = "https://example.com/video.mp4"
        assert browser_compatible_video_url(u) == u

    def test_api_uploads_path_unchanged(self):
        u = "/api/uploads/vid-abc-20260101120000-deadbeef.mp4"
        assert browser_compatible_video_url(u) == u

    def test_none_returns_none(self):
        assert browser_compatible_video_url(None) is None

    def test_empty_string_unchanged(self):
        assert browser_compatible_video_url("") == ""

    def test_cloudinary_gets_transform_injected(self):
        u = "https://res.cloudinary.com/demo/video/upload/v1234567890/acechasers/post/vid-xyz.mp4"
        out = browser_compatible_video_url(u)
        assert "/upload/f_mp4,vc_h264,q_auto/" in out
        assert out == (
            "https://res.cloudinary.com/demo/video/upload/f_mp4,vc_h264,q_auto/"
            "v1234567890/acechasers/post/vid-xyz.mp4"
        )

    def test_cloudinary_with_existing_transform_not_double_injected(self):
        # The legacy pre-q_auto transform must still be recognized so that
        # any cached URLs from a previous deploy aren't double-injected.
        u = (
            "https://res.cloudinary.com/demo/video/upload/f_mp4,vc_h264/"
            "v1234567890/acechasers/post/vid-xyz.mp4"
        )
        out = browser_compatible_video_url(u)
        assert out == u
        assert out.count("f_mp4,vc_h264") == 1

    def test_cloudinary_with_new_transform_not_double_injected(self):
        u = (
            "https://res.cloudinary.com/demo/video/upload/f_mp4,vc_h264,q_auto/"
            "v1234567890/acechasers/post/vid-xyz.mp4"
        )
        out = browser_compatible_video_url(u)
        assert out == u
        assert out.count("f_mp4,vc_h264") == 1


# --- 2. Feed rewrite path via seeded DB doc --------------------------------

class TestFeedVideoUrlRewrite:
    def test_feed_rewrites_cloudinary_video_url(self, user_a):
        """Seed a fake post doc with a Cloudinary-shaped video_path directly
        into Mongo, then verify GET /api/feed returns the transformed URL."""
        import asyncio
        sys.path.insert(0, "/app/backend")
        from db import get_db  # noqa

        cloudinary_url = (
            "https://res.cloudinary.com/demo/video/upload/v1700000000/"
            "acechasers/post/vid-seed-iter22.mp4"
        )
        post_id = f"seed-i22-{uuid.uuid4().hex[:10]}"

        async def _seed():
            db = get_db()
            await db.posts.insert_one({
                "id": post_id,
                "author_uid": user_a["uid"],
                "body": "iter22 seed video post",
                "image_path": None,
                "video_path": cloudinary_url,
                "visibility": "public",
                "kind": "post",
                "created_at": "2099-01-01T00:00:00+00:00",  # sort to top
            })

        async def _cleanup():
            db = get_db()
            await db.posts.delete_one({"id": post_id})

        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = requests.get(
                f"{BASE_URL}/api/feed?limit=5",
                headers=_h(user_a["id_token"]),
                timeout=20,
            )
            assert r.status_code == 200, r.text
            posts = r.json().get("posts", [])
            match = next((p for p in posts if p["id"] == post_id), None)
            assert match is not None, "seeded post not in feed"
            vu = match["video_url"]
            assert "/upload/f_mp4,vc_h264,q_auto/" in vu, f"transform missing: {vu}"
            assert "res.cloudinary.com" in vu
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup())

    def test_feed_local_video_path_unchanged(self, user_a):
        """A /api/uploads/ style path should NOT get the transform."""
        import asyncio
        from db import get_db  # noqa

        post_id = f"seed-i22-local-{uuid.uuid4().hex[:10]}"

        async def _seed():
            db = get_db()
            await db.posts.insert_one({
                "id": post_id,
                "author_uid": user_a["uid"],
                "body": "iter22 local video",
                "image_path": None,
                "video_path": "vid-local-iter22.mp4",  # bare filename
                "visibility": "public",
                "kind": "post",
                "created_at": "2099-01-01T00:00:01+00:00",
            })

        async def _cleanup():
            db = get_db()
            await db.posts.delete_one({"id": post_id})

        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = requests.get(
                f"{BASE_URL}/api/feed?limit=5",
                headers=_h(user_a["id_token"]),
                timeout=20,
            )
            assert r.status_code == 200
            posts = r.json().get("posts", [])
            match = next((p for p in posts if p["id"] == post_id), None)
            assert match is not None
            vu = match["video_url"]
            assert vu == "/api/uploads/vid-local-iter22.mp4"
            assert "f_mp4,vc_h264" not in vu
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup())


# --- 3. PATCH /api/posts/{id} ----------------------------------------------

@pytest.fixture
def post_by_a(user_a):
    """Create a fresh text-only post by user_a."""
    r = requests.post(
        f"{BASE_URL}/api/posts",
        data={"body": "original text", "visibility": "public", "kind": "post"},
        headers=_h(user_a["id_token"]),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    p = r.json()
    yield p
    try:
        requests.delete(
            f"{BASE_URL}/api/posts/{p['id']}",
            headers=_h(user_a["id_token"]),
            timeout=10,
        )
    except Exception:
        pass


class TestEditPost:
    def test_new_post_has_edited_at_null(self, post_by_a):
        assert "edited_at" in post_by_a
        assert post_by_a["edited_at"] is None
        assert post_by_a["body"] == "original text"

    def test_owner_can_edit_body(self, user_a, post_by_a):
        r = requests.patch(
            f"{BASE_URL}/api/posts/{post_by_a['id']}",
            json={"body": "edited text"},
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["body"] == "edited text"
        assert p["edited_at"] is not None
        assert isinstance(p["edited_at"], str)
        assert p["created_at"] == post_by_a["created_at"]
        assert p["is_mine"] is True
        assert p["author"]["uid"] == user_a["uid"]
        # Hydrated counters still present
        assert "nice_count" in p and "comment_count" in p

        # Persistence: GET /api/feed shows the edited body + edited_at set
        r2 = requests.get(
            f"{BASE_URL}/api/feed?limit=20",
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r2.status_code == 200
        posts = r2.json().get("posts", [])
        match = next((x for x in posts if x["id"] == post_by_a["id"]), None)
        assert match is not None
        assert match["body"] == "edited text"
        assert match["edited_at"] is not None

    def test_non_owner_gets_404(self, user_b, post_by_a):
        r = requests.patch(
            f"{BASE_URL}/api/posts/{post_by_a['id']}",
            json={"body": "hacker text"},
            headers=_h(user_b["id_token"]),
            timeout=20,
        )
        assert r.status_code == 404, r.text
        detail = r.json().get("detail", "")
        assert "not found" in detail.lower() or "not yours" in detail.lower()

    def test_empty_body_rejected(self, user_a, post_by_a):
        r = requests.patch(
            f"{BASE_URL}/api/posts/{post_by_a['id']}",
            json={"body": ""},
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code in (400, 422), r.text

    def test_nonexistent_post_404(self, user_a):
        r = requests.patch(
            f"{BASE_URL}/api/posts/does-not-exist-xyz",
            json={"body": "whatever"},
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 404

    def test_delete_still_works(self, user_a):
        # Create + delete
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "to be deleted", "visibility": "public", "kind": "post"},
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200
        pid = r.json()["id"]
        r2 = requests.delete(
            f"{BASE_URL}/api/posts/{pid}",
            headers=_h(user_a["id_token"]),
            timeout=10,
        )
        assert r2.status_code == 200
        # PATCH after delete -> 404
        r3 = requests.patch(
            f"{BASE_URL}/api/posts/{pid}",
            json={"body": "zombie"},
            headers=_h(user_a["id_token"]),
            timeout=10,
        )
        assert r3.status_code == 404
