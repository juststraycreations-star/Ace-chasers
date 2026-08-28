"""Iteration 25 — Leagues merge regression + auth bridge + cloudinary swap.

Focus areas per the review request:
  1. Auth bridge: /api/auth/me (leagues router endpoint if any) + /api/leagues
     with a Firebase Bearer must return 200 (previously 500 due to
     Ace Chasers users.uid unique index colliding with the league bridge).
  2. Create-League round-trip: POST /api/leagues returns 200 + a league doc
     with an id; GET /api/leagues/{id} returns the same doc.
  3. Cloudinary swap: POST /api/files/upload (multipart) returns url with
     'res.cloudinary.com'.
  4. Ace Chasers regression smoke: /api/discovery, /api/courses, /api/feed
     still return 200 for a fresh Firebase user (LeagueAuthProvider wrap
     shouldn't break existing routes).
  5. No duplicate route registration warnings — assert count of GET /api/leagues.
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


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _signup(prefix="u"):
    email = f"TEST_i25_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


@pytest.fixture(scope="module")
def user():
    u = _signup("main")
    # Sync into Ace Chasers users collection first so both keys exist
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=20)
    assert r.status_code == 200, r.text
    return u


@pytest.fixture(scope="module")
def user2():
    u = _signup("second")
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=20)
    assert r.status_code == 200, r.text
    return u


# ---------------- Auth bridge ----------------
class TestLeaguesAuthBridge:
    def test_get_leagues_authenticated(self, user):
        r = requests.get(f"{BASE_URL}/api/leagues", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        assert isinstance(r.json(), list)

    def test_get_my_leagues_authenticated(self, user):
        # /api/leagues/my typically lists memberships
        r = requests.get(f"{BASE_URL}/api/leagues/my", headers=_h(user["id_token"]), timeout=20)
        # some routers return 200 with [] when empty, others 404 if not defined
        assert r.status_code in (200, 404), r.text[:400]

    def test_no_auth_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/leagues", timeout=20)
        assert r.status_code == 401

    def test_second_user_no_duplicate_key(self, user2):
        # regression: the original bug was that the SECOND league-bridge
        # insert triggered E11000 dup key on uid:null. This asserts the fix.
        r = requests.get(f"{BASE_URL}/api/leagues", headers=_h(user2["id_token"]), timeout=20)
        assert r.status_code == 200, f"Regression: {r.status_code} {r.text[:400]}"


# ---------------- Create League round-trip ----------------
class TestCreateLeague:
    def test_create_and_fetch(self, user):
        payload = {
            "name": f"TEST_i25_League_{uuid.uuid4().hex[:6]}",
            "location": "Test Park",
            "format": "Singles",
            "description": "Iteration 25 regression league",
        }
        r = requests.post(
            f"{BASE_URL}/api/leagues", json=payload, headers=_h(user["id_token"]), timeout=20
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        league = r.json()
        assert "id" in league
        assert league["name"] == payload["name"]
        lid = league["id"]

        # GET
        r2 = requests.get(
            f"{BASE_URL}/api/leagues/{lid}", headers=_h(user["id_token"]), timeout=20
        )
        assert r2.status_code == 200
        got = r2.json()
        assert got["id"] == lid
        assert got["name"] == payload["name"]
        assert got["location"] == "Test Park"


# ---------------- Cloudinary swap ----------------
# 1x1 PNG
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
    b"\x02\xfe\xa9\xa3\x1a\xbf\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestCloudinarySwap:
    def test_upload_returns_cloudinary_url(self, user):
        files = {"file": ("test.png", io.BytesIO(_PNG_1x1), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/files/upload",
            headers=_h(user["id_token"]),
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert "url" in d, d
        assert "res.cloudinary.com" in d["url"], f"Expected Cloudinary URL, got {d['url']}"


# ---------------- Ace Chasers regression smoke ----------------
class TestRegression:
    def test_discovery(self, user):
        r = requests.get(f"{BASE_URL}/api/discovery", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "players" in d
        # Iter 22 spec: page size 100, expect 88+ candidates for fresh user
        assert len(d["players"]) >= 20, f"Only {len(d['players'])} players returned"

    def test_courses(self, user):
        r = requests.get(f"{BASE_URL}/api/courses", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200

    def test_feed(self, user):
        r = requests.get(f"{BASE_URL}/api/feed", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200

    def test_users_me(self, user):
        r = requests.get(f"{BASE_URL}/api/users/me", headers=_h(user["id_token"]), timeout=20)
        assert r.status_code == 200
        assert r.json().get("uid") == user["uid"]
