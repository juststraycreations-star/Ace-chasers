"""Comprehensive backend API tests for Ace Chasers.

Uses Firebase Identity Toolkit REST API to mint real ID tokens for two
ephemeral test users, then exercises every public endpoint.
"""
from __future__ import annotations

import io
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
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")

IDENTITY_TOOLKIT = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
)
DELETE_ACCOUNT = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"
)


def _signup_firebase(email: str, password: str = "demo1234") -> dict:
    r = requests.post(
        IDENTITY_TOOLKIT,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _delete_firebase(id_token: str) -> None:
    try:
        requests.post(DELETE_ACCOUNT, json={"idToken": id_token}, timeout=10)
    except Exception:
        pass


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- Fixtures ----------

@pytest.fixture(scope="session")
def user_a():
    email = f"TEST_a_{uuid.uuid4().hex[:8]}@example.com"
    data = _signup_firebase(email)
    yield {"email": email, "id_token": data["idToken"], "uid": data["localId"]}
    _delete_firebase(data["idToken"])


@pytest.fixture(scope="session")
def user_b():
    email = f"TEST_b_{uuid.uuid4().hex[:8]}@example.com"
    data = _signup_firebase(email)
    yield {"email": email, "id_token": data["idToken"], "uid": data["localId"]}
    _delete_firebase(data["idToken"])


# ---------- Health / config ----------

class TestHealthAndConfig:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_config(self):
        r = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "require_invite" in body
        assert body["require_invite"] is False


# ---------- Auth wall ----------

class TestAuthWall:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/users/me"),
            ("PUT", "/api/users/me"),
            ("GET", "/api/discovery"),
            ("GET", "/api/likes"),
            ("GET", "/api/feed"),
            ("POST", "/api/posts"),
            ("POST", "/api/swipes"),
            ("POST", "/api/auth/sync"),
            ("GET", "/api/users/seed-sarah"),
        ],
    )
    def test_no_token_returns_401(self, method, path):
        r = requests.request(method, f"{BASE_URL}{path}", timeout=10)
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}"

    def test_bad_token_returns_401(self):
        r = requests.get(
            f"{BASE_URL}/api/users/me",
            headers={"Authorization": "Bearer not.a.valid.token"},
            timeout=10,
        )
        assert r.status_code == 401


class TestAdminWall:
    def test_admin_invites_requires_key(self):
        r = requests.get(f"{BASE_URL}/api/admin/invites", timeout=10)
        assert r.status_code == 401

    def test_admin_invites_wrong_key(self):
        r = requests.get(
            f"{BASE_URL}/api/admin/invites",
            headers={"X-Admin-Key": "wrong"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_admin_invites_correct_key(self):
        r = requests.get(
            f"{BASE_URL}/api/admin/invites",
            headers={"X-Admin-Key": ADMIN_API_KEY},
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Auth sync + user profile ----------

class TestAuthSyncAndProfile:
    def test_auth_sync_creates_user(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/auth/sync",
            json={},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["uid"] == user_a["uid"]
        assert (body["email"] or "").lower() == user_a["email"].lower()
        # New user defaults seeded
        assert "casual play" in (body.get("interests") or [])

    def test_get_me(self, user_a):
        r = requests.get(
            f"{BASE_URL}/api/users/me",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["uid"] == user_a["uid"]

    def test_update_me_and_persist(self, user_a):
        payload = {
            "favoriteFrisbee": "Innova Destroyer",
            "location": "Austin, TX",
            "bio": "Test bio for QA",
        }
        r = requests.put(
            f"{BASE_URL}/api/users/me",
            json=payload,
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["favoriteFrisbee"] == "Innova Destroyer"
        assert body["location"] == "Austin, TX"
        assert body["bio"] == "Test bio for QA"

        # Persist check
        r2 = requests.get(
            f"{BASE_URL}/api/users/me",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r2.json()["favoriteFrisbee"] == "Innova Destroyer"

    def test_public_profile_strips_email(self, user_a, user_b):
        # Sync user_b so the doc exists.
        requests.post(
            f"{BASE_URL}/api/auth/sync",
            json={},
            headers=_auth_headers(user_b["id_token"]),
            timeout=15,
        )
        # A views B's profile -> email must be None
        r = requests.get(
            f"{BASE_URL}/api/users/{user_b['uid']}",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["uid"] == user_b["uid"]
        assert body.get("email") is None, "Email leaked to non-self viewer"
        assert body.get("emailVerified") is False

        # Self view returns email
        r2 = requests.get(
            f"{BASE_URL}/api/users/{user_a['uid']}",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r2.status_code == 200
        assert (r2.json().get("email") or "").lower() == user_a["email"].lower()

    def test_get_unknown_user_404(self, user_a):
        r = requests.get(
            f"{BASE_URL}/api/users/no-such-user-xyz",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 404


# ---------- Discovery / swipes / likes ----------

class TestDiscoveryAndLikes:
    def test_discovery_excludes_self(self, user_a):
        r = requests.get(
            f"{BASE_URL}/api/discovery",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert "players" in body and "next_cursor" in body
        # Walk pages until we find a seed user or exhaust (discovery is
        # sorted newest-first; with many test signups seeds may be on a
        # later page).
        all_uids = set()
        for p in body["players"]:
            all_uids.add(p["uid"])
        cursor = body["next_cursor"]
        for _ in range(10):
            if cursor is None or any(u in all_uids for u in ("seed-sarah", "seed-amanda", "seed-jessica")):
                break
            r2 = requests.get(
                f"{BASE_URL}/api/discovery?before={cursor}",
                headers=_auth_headers(user_a["id_token"]),
                timeout=15,
            )
            assert r2.status_code == 200
            b2 = r2.json()
            for p in b2["players"]:
                all_uids.add(p["uid"])
            cursor = b2["next_cursor"]
        assert user_a["uid"] not in all_uids
        assert any(u in all_uids for u in ("seed-sarah", "seed-amanda", "seed-jessica"))

    def test_like_seed_sarah_creates_match(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": "seed-sarah", "action": "like"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["matched"] is True, "seed-sarah auto-likes, should match"

    def test_likes_list_shows_match(self, user_a):
        r = requests.get(
            f"{BASE_URL}/api/likes",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        likes = r.json()
        sarah = next((row for row in likes if row["player"]["uid"] == "seed-sarah"), None)
        assert sarah is not None
        assert sarah["matched"] is True
        assert sarah["friended"] is False

    def test_friend_match(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/matches/seed-sarah/friend",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_swipe_self_400(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": user_a["uid"], "action": "like"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400

    def test_swipe_unknown_target_404(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": "no-such-uid-xyz", "action": "like"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 404

    def test_remove_like(self, user_a):
        # Like seed-jessica (no auto-like) so we can remove it.
        requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": "seed-jessica", "action": "like"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        r = requests.delete(
            f"{BASE_URL}/api/likes/seed-jessica",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200

    def test_pass_swipe(self, user_a, user_b):
        # ensure user_b is synced
        requests.post(
            f"{BASE_URL}/api/auth/sync",
            json={},
            headers=_auth_headers(user_b["id_token"]),
            timeout=15,
        )
        r = requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": user_b["uid"], "action": "pass"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["matched"] is False


# ---------- Posts / Feed ----------

class TestPostsAndFeed:
    POST_IDS: list[str] = []

    def test_create_public_text_post(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_public hello world", "visibility": "public"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["body"] == "TEST_public hello world"
        assert body["visibility"] == "public"
        assert body["author"]["uid"] == user_a["uid"]
        assert body["is_mine"] is True
        TestPostsAndFeed.POST_IDS.append(body["id"])

    def test_empty_post_rejected(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "", "visibility": "public"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400

    def test_create_friends_only_post(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_secret friends only", "visibility": "friends_only"},
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["visibility"] == "friends_only"
        TestPostsAndFeed.POST_IDS.append(r.json()["id"])

    def test_friends_only_invisible_to_stranger(self, user_a, user_b):
        # User B is NOT friends with user_a, even with a pass swipe.
        r = requests.get(
            f"{BASE_URL}/api/feed",
            headers=_auth_headers(user_b["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        posts = r.json()["posts"]
        for p in posts:
            if p["author"]["uid"] == user_a["uid"]:
                assert (
                    p["visibility"] != "friends_only"
                ), "DATA LEAK: friends_only post visible to non-friend"

    def test_own_friends_only_visible_to_self(self, user_a):
        r = requests.get(
            f"{BASE_URL}/api/feed",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        posts = r.json()["posts"]
        kinds = {p["visibility"] for p in posts if p["author"]["uid"] == user_a["uid"]}
        assert "friends_only" in kinds and "public" in kinds

    def test_post_with_image(self, user_a):
        # 1x1 PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03"
            b"\x00\x01\x84\xd2\xb1\x82\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"image": ("test.png", io.BytesIO(png), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_with image", "visibility": "public"},
            files=files,
            headers=_auth_headers(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["image_url"]
        # Either Cloudinary HTTPS URL OR legacy /api/uploads/ path
        assert body["image_url"].startswith("https://res.cloudinary.com/") or body["image_url"].startswith("/api/uploads/")
        TestPostsAndFeed.POST_IDS.append(body["id"])

        # Verify the image is fetchable
        if body["image_url"].startswith("http"):
            ir = requests.get(body["image_url"], timeout=15)
        else:
            ir = requests.get(f"{BASE_URL}{body['image_url']}", timeout=15)
        assert ir.status_code == 200
        assert ir.headers.get("content-type", "").startswith("image/")

    def test_reject_oversize_image(self, user_a):
        big = b"a" * (6 * 1024 * 1024)  # 6MB
        files = {"image": ("big.png", io.BytesIO(big), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_too big", "visibility": "public"},
            files=files,
            headers=_auth_headers(user_a["id_token"]),
            timeout=30,
        )
        assert r.status_code == 400

    def test_reject_unsupported_image_type(self, user_a):
        files = {"image": ("evil.txt", io.BytesIO(b"hi"), "text/plain")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_bad type", "visibility": "public"},
            files=files,
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400

    def test_feed_pagination(self, user_a):
        # Create enough posts to require pagination
        for i in range(22):
            requests.post(
                f"{BASE_URL}/api/posts",
                data={"body": f"TEST_pager {i}", "visibility": "public"},
                headers=_auth_headers(user_a["id_token"]),
                timeout=15,
            )
        r = requests.get(
            f"{BASE_URL}/api/feed?limit=20",
            headers=_auth_headers(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["posts"]) == 20
        assert body["next_cursor"] is not None

        r2 = requests.get(
            f"{BASE_URL}/api/feed?limit=20&before={body['next_cursor']}",
            headers=_auth_headers(user_a["id_token"]),
            timeout=20,
        )
        assert r2.status_code == 200
        ids_page1 = {p["id"] for p in body["posts"]}
        ids_page2 = {p["id"] for p in r2.json()["posts"]}
        assert ids_page1.isdisjoint(ids_page2)

    def test_delete_own_post(self, user_a):
        if not TestPostsAndFeed.POST_IDS:
            pytest.skip("No post id captured")
        pid = TestPostsAndFeed.POST_IDS[0]
        r = requests.delete(
            f"{BASE_URL}/api/posts/{pid}",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200

    def test_delete_others_post_404(self, user_a, user_b):
        # User B creates a post; user A tries to delete it
        cr = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_b post", "visibility": "public"},
            headers=_auth_headers(user_b["id_token"]),
            timeout=15,
        )
        pid = cr.json()["id"]
        r = requests.delete(
            f"{BASE_URL}/api/posts/{pid}",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 404


# ---------- Discovery: latest_post snippet ----------

class TestDiscoveryRecentPost:
    def test_recent_post_only_public(self, user_a, user_b):
        # B creates a friends_only post first, then a public post.
        requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_b friends only secret", "visibility": "friends_only"},
            headers=_auth_headers(user_b["id_token"]),
            timeout=15,
        )
        time.sleep(0.05)
        requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_b public visible", "visibility": "public"},
            headers=_auth_headers(user_b["id_token"]),
            timeout=15,
        )

        r = requests.get(
            f"{BASE_URL}/api/discovery",
            headers=_auth_headers(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        items = r.json()["players"]
        b_card = next((p for p in items if p["uid"] == user_b["uid"]), None)
        if b_card is None:
            pytest.skip("user_b not in user_a's discovery (already swiped)")
        rp = b_card.get("recent_post")
        assert rp is not None
        assert "secret" not in (rp.get("body") or "").lower()
