"""Iteration 28 — Verify signup end-to-end unblocked (P0), and that all
core auth-required endpoints return 200 for a fresh Firebase signup.

Covers:
  - Firebase Identity Toolkit signUp works with real prod API key
  - POST /api/auth/sync => 200 (creates user doc)
  - GET  /api/users/me => 200 (profile shape sane)
  - GET  /api/discovery => 200 (list)
  - GET  /api/feed => 200 (list)
  - GET  /api/courses => 200
  - GET  /api/messages/threads => 200
  - GET  /api/leagues => 200

No 500s / ValidationError on User model for new users.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def new_user():
    email = f"TEST_i28_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=25,
    )
    assert r.status_code == 200, f"Firebase signUp failed: {r.text}"
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


class TestSignupUnblocked:
    """Primary P0: fresh signup + full auth-required surface is 200s."""

    def test_auth_sync_ok(self, new_user):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/auth/sync", json={},
            headers=_h(new_user["id_token"]), timeout=25,
        )
        elapsed_ms = (time.time() - t0) * 1000
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("uid") == new_user["uid"] or data.get("id") == new_user["uid"] or "email" in data
        # sanity: it's not painfully slow (was ~200ms in prod)
        assert elapsed_ms < 8000, f"auth/sync too slow: {elapsed_ms:.0f}ms"

    def test_users_me_returns_profile(self, new_user):
        r = requests.get(
            f"{BASE_URL}/api/users/me", headers=_h(new_user["id_token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p.get("email") == new_user["email"] or "email" in p

    def test_discovery_200(self, new_user):
        r = requests.get(
            f"{BASE_URL}/api/discovery", headers=_h(new_user["id_token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, (list, dict))
        if isinstance(body, dict):
            assert "players" in body

    def test_feed_200(self, new_user):
        r = requests.get(
            f"{BASE_URL}/api/feed", headers=_h(new_user["id_token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        # feed can be list or dict
        assert isinstance(r.json(), (list, dict))

    def test_courses_200(self, new_user):
        r = requests.get(
            f"{BASE_URL}/api/courses", headers=_h(new_user["id_token"]), timeout=20,
        )
        assert r.status_code == 200, r.text

    def test_leagues_200(self, new_user):
        r = requests.get(
            f"{BASE_URL}/api/leagues", headers=_h(new_user["id_token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_messages_threads_200(self, new_user):
        r = requests.get(
            f"{BASE_URL}/api/messages/threads",
            headers=_h(new_user["id_token"]), timeout=20,
        )
        assert r.status_code == 200, r.text


class TestBuildArtifacts:
    """Verify the vite build produced route-split chunks under dist/assets/."""

    def test_chunk_manifest(self):
        assets = "/app/frontend/dist/assets"
        assert os.path.isdir(assets), "dist/assets missing — run yarn build"
        names = os.listdir(assets)
        joined = " ".join(names)

        # Route chunks exist
        for prefix in [
            "index-", "Feed-", "Discovery-", "LeagueDashboard-",
            "LeagueDetail-", "RoundScorecard-", "Courses-", "Profile-",
            "vendor-charts-",
        ]:
            assert any(n.startswith(prefix) for n in names), \
                f"missing chunk {prefix}*: {joined}"

        # index main bundle < 100KB
        index_files = [n for n in names if n.startswith("index-") and n.endswith(".js")]
        assert index_files, "no index-*.js"
        idx_size = os.path.getsize(os.path.join(assets, index_files[0]))
        assert idx_size < 100 * 1024, f"index too large: {idx_size} bytes"

        # vendor-charts should NOT be in main index — enforce it is a separate chunk
        vc = [n for n in names if n.startswith("vendor-charts-") and n.endswith(".js")]
        assert vc, "vendor-charts chunk missing"
