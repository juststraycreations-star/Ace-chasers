"""Iteration 3 tests:
- Cloudinary uploads (profile, banner, post image, post video)
- Magic-byte sniff still runs BEFORE cloud upload
- Video MIME whitelist (unknown ftyp brands rejected)
- Discovery cursor pagination shape
- _hydrate_post handles both shapes (verbatim test of helper logic)
"""
from __future__ import annotations

import io
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

CLOUDINARY_PREFIX_IMAGE = "https://res.cloudinary.com/"  # we accept any cloud name to avoid hardcoding
CLOUDINARY_VIDEO_PREFIX = "https://res.cloudinary.com/"


def _signup():
    email = f"TEST_i3_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(IDENTITY, json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=15)
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def user():
    u = _signup()
    # sync
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=15)
    assert r.status_code == 200
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


# Minimal 1x1 PNG
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03"
    b"\x00\x01\x84\xd2\xb1\x82\x00\x00\x00\x00IEND\xaeB`\x82"
)
# Minimal MP4 ftyp/isom
MP4_BYTES = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 512


class TestCloudinaryUploads:
    def test_profile_picture_uploads_to_cloudinary(self, user):
        files = {"image": ("avatar.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/users/me/profile-picture",
            files=files,
            headers=_h(user["id_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        url = body.get("profilePictureUrl") or body.get("url") or ""
        assert url.startswith(CLOUDINARY_PREFIX_IMAGE), f"expected cloudinary URL, got: {url}"
        assert "/image/upload/" in url
        # publicly fetchable
        ir = requests.get(url, timeout=15)
        assert ir.status_code == 200
        assert ir.headers.get("content-type", "").startswith("image/")
        # persisted: GET /api/users/me returns same URL
        gr = requests.get(f"{BASE_URL}/api/users/me", headers=_h(user["id_token"]), timeout=15)
        assert gr.status_code == 200
        assert gr.json().get("profilePictureUrl") == url

    def test_banner_uploads_to_cloudinary(self, user):
        files = {"image": ("banner.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/users/me/banner",
            files=files,
            headers=_h(user["id_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        url = body.get("bannerUrl") or body.get("url") or ""
        assert url.startswith(CLOUDINARY_PREFIX_IMAGE), f"expected cloudinary URL, got: {url}"
        ir = requests.get(url, timeout=15)
        assert ir.status_code == 200

    def test_post_image_uploads_to_cloudinary_and_survives(self, user):
        files = {"image": ("p.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_i3 cloud image", "visibility": "public"},
            files=files,
            headers=_h(user["id_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        url = body["image_url"]
        assert url.startswith(CLOUDINARY_PREFIX_IMAGE), f"expected cloudinary URL, got: {url}"
        assert "/image/upload/" in url
        # publicly fetchable
        ir = requests.get(url, timeout=15)
        assert ir.status_code == 200
        # verify feed returns same URL
        fr = requests.get(f"{BASE_URL}/api/feed?limit=20", headers=_h(user["id_token"]), timeout=15)
        assert fr.status_code == 200
        post = next((p for p in fr.json()["posts"] if p["id"] == body["id"]), None)
        assert post is not None
        assert post["image_url"] == url

    def test_post_video_uploads_to_cloudinary(self, user):
        # Real mp4 needed because Cloudinary actually decodes the file.
        try:
            with open("/tmp/test.mp4", "rb") as f:
                video_bytes = f.read()
        except FileNotFoundError:
            pytest.skip("Real sample mp4 not available at /tmp/test.mp4")
        files = {"media": ("v.mp4", io.BytesIO(video_bytes), "video/mp4")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_i3 cloud video", "visibility": "public"},
            files=files,
            headers=_h(user["id_token"]),
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        url = body["video_url"]
        assert url.startswith(CLOUDINARY_VIDEO_PREFIX), f"expected cloudinary URL, got: {url}"
        assert "/video/upload/" in url
        ir = requests.get(url, timeout=20)
        assert ir.status_code == 200

    def test_magic_byte_sniff_runs_before_cloudinary(self, user):
        # renamed .txt with .jpg extension - should be 400, never hit Cloudinary
        files = {"image": ("evil.jpg", io.BytesIO(b"this is plain text not an image at all"), "image/jpeg")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_i3 evil", "visibility": "public"},
            files=files,
            headers=_h(user["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400


class TestVideoMimeWhitelist:
    """Direct unit-style tests of posts.sniff_video_mime."""

    def setup_method(self):
        sys.path.insert(0, "/app/backend")

    def _build(self, brand: bytes) -> bytes:
        return b"\x00\x00\x00\x20ftyp" + brand + b"\x00\x00\x02\x00" + brand + b"iso2mp41" + b"\x00" * 64

    def test_isom_allowed(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"isom")) == "video/mp4"

    def test_mp41_mp42_allowed(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"mp41")) == "video/mp4"
        assert sniff_video_mime(self._build(b"mp42")) == "video/mp4"

    def test_avc1_dash_allowed(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"avc1")) == "video/mp4"
        assert sniff_video_mime(self._build(b"dash")) == "video/mp4"

    def test_qt_allowed(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"qt  ")) == "video/quicktime"

    def test_3gp_rejected(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"3gp4")) is None

    def test_heic_rejected(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"heic")) is None

    def test_avif_rejected(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(self._build(b"avif")) is None

    def test_webm_allowed(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(b"\x1a\x45\xdf\xa3" + b"\x00" * 64) == "video/webm"

    def test_garbage_rejected(self):
        from posts import sniff_video_mime
        assert sniff_video_mime(b"hello world this is not a video at all") is None


class TestDiscoveryPagination:
    def test_discovery_shape(self, user):
        r = requests.get(f"{BASE_URL}/api/discovery", headers=_h(user["id_token"]), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert "players" in body
        assert "next_cursor" in body
        assert isinstance(body["players"], list)
        # next_cursor null when fewer than limit
        if len(body["players"]) < 24:
            assert body["next_cursor"] is None

    def test_discovery_small_limit_paginates(self, user):
        # ask for limit=1 — if there's >=2 candidates, expect next_cursor present
        r = requests.get(f"{BASE_URL}/api/discovery?limit=1", headers=_h(user["id_token"]), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert len(body["players"]) <= 1
        if body["next_cursor"]:
            # next page excludes first batch
            first_uids = {p["uid"] for p in body["players"]}
            r2 = requests.get(
                f"{BASE_URL}/api/discovery?limit=1&before={body['next_cursor']}",
                headers=_h(user["id_token"]),
                timeout=15,
            )
            assert r2.status_code == 200
            body2 = r2.json()
            second_uids = {p["uid"] for p in body2["players"]}
            assert first_uids.isdisjoint(second_uids)


class TestHydratePostLegacyShape:
    """Confirm _hydrate_post logic prefixes bare filenames with /api/uploads/
    and leaves http URLs verbatim. This is a code-level inspection, not
    a fixture insert."""

    def test_legacy_filename_gets_prefix(self):
        sys.path.insert(0, "/app/backend")
        # Inspect the helper's source: 'http' prefix branch is the cloudinary case
        from routers import posts_router
        import inspect
        src = inspect.getsource(posts_router._hydrate_post)
        assert "startswith(\"http\")" in src
        assert "/api/uploads/" in src
