"""Tests for the new features added in iteration 2:

- POST /api/posts accepting video uploads (field `media` or `image`)
- Magic-byte sniffing rejects renamed .txt files
- Friend request endpoints + auto-accept logic
- GET /api/inbox aggregation (no duplicates with friend-requests)
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")

IDENTITY_TOOLKIT = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
)
DELETE_ACCOUNT = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"
)


def _signup() -> dict:
    email = f"TEST_n_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY_TOOLKIT,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return {"email": email, "id_token": data["idToken"], "uid": data["localId"]}


def _delete(id_token: str) -> None:
    try:
        requests.post(DELETE_ACCOUNT, json={"idToken": id_token}, timeout=10)
    except Exception:
        pass


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _sync(u: dict) -> None:
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=15)
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def user_a():
    u = _signup()
    _sync(u)
    yield u
    _delete(u["id_token"])


@pytest.fixture(scope="module")
def user_b():
    u = _signup()
    _sync(u)
    yield u
    _delete(u["id_token"])


@pytest.fixture(scope="module")
def user_c():
    u = _signup()
    _sync(u)
    yield u
    _delete(u["id_token"])


# ---------- Video upload ----------

# minimal ftyp/mp4 header (sniff_video_mime checks data[4:8]=='ftyp')
MP4_BYTES = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 64
WEBM_BYTES = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


class TestVideoUpload:
    def test_post_with_mp4_via_media(self, user_a):
        files = {"media": ("clip.mp4", io.BytesIO(MP4_BYTES), "video/mp4")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_video mp4", "visibility": "public"},
            files=files,
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("video_url"), f"expected video_url in {body}"
        assert body["video_url"].startswith("/api/uploads/")
        assert body["video_url"].endswith(".mp4")
        assert body.get("image_url") in (None, "")
        # Fetchable
        vr = requests.get(f"{BASE_URL}{body['video_url']}", timeout=15)
        assert vr.status_code == 200

    def test_post_with_webm_via_media(self, user_a):
        files = {"media": ("clip.webm", io.BytesIO(WEBM_BYTES), "video/webm")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_video webm", "visibility": "public"},
            files=files,
            headers=_h(user_a["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["video_url"].endswith(".webm")

    def test_reject_oversize_video(self, user_a):
        # 26 MB > 25MB limit but with valid mp4 magic
        big = MP4_BYTES + b"\x00" * (26 * 1024 * 1024)
        files = {"media": ("big.mp4", io.BytesIO(big), "video/mp4")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_big video", "visibility": "public"},
            files=files,
            headers=_h(user_a["id_token"]),
            timeout=60,
        )
        assert r.status_code == 400
        assert "25" in r.text or "exceeds" in r.text.lower()

    def test_reject_renamed_txt_as_image(self, user_a):
        # Bytes are 'hello' but the filename pretends to be png/mp4 -> magic byte sniff fails
        files = {"image": ("evil.png", io.BytesIO(b"hello world not an image"), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_renamed", "visibility": "public"},
            files=files,
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400

    def test_reject_renamed_txt_as_video(self, user_a):
        files = {"media": ("evil.mp4", io.BytesIO(b"hello world not a video"), "video/mp4")}
        r = requests.post(
            f"{BASE_URL}/api/posts",
            data={"body": "TEST_renamed video", "visibility": "public"},
            files=files,
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400


# ---------- Friend requests ----------

class TestFriendRequests:
    def test_send_friend_request_creates_pending(self, user_a, user_b):
        # A -> B. B has not liked A and has not sent FR.
        # NOTE: seed users auto-like every new user, but A and B don't auto-like each other.
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_b['uid']}",
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        # No prior interaction from B -> should NOT match
        assert body["matched"] is False
        assert body["friended"] is False

    def test_pending_request_appears_in_inbox(self, user_a, user_b):
        # B should see A's pending request in inbox.incoming_friend_requests
        r = requests.get(f"{BASE_URL}/api/inbox", headers=_h(user_b["id_token"]), timeout=15)
        assert r.status_code == 200
        body = r.json()
        fr_uids = {fr["from_user"]["uid"] for fr in body["incoming_friend_requests"]}
        assert user_a["uid"] in fr_uids
        # And NOT duplicated in incoming_likes
        like_uids = {lk["from_user"]["uid"] for lk in body["incoming_likes"]}
        assert user_a["uid"] not in like_uids, "Pending FR duplicated in incoming_likes"

    def test_inbox_excludes_mutual_likes(self, user_a):
        # User A has matched with seed-sarah (auto-like). Sarah should NOT be in incoming_likes.
        requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": "seed-sarah", "action": "like"},
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        r = requests.get(f"{BASE_URL}/api/inbox", headers=_h(user_a["id_token"]), timeout=15)
        assert r.status_code == 200
        like_uids = {lk["from_user"]["uid"] for lk in r.json()["incoming_likes"]}
        assert "seed-sarah" not in like_uids, "Mutual like should not appear in incoming_likes"

    def test_accept_friend_request_creates_match(self, user_a, user_b):
        # B accepts A's pending request.
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_a['uid']}/accept",
            headers=_h(user_b["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text

        # The pending request is gone from B's inbox.
        ir = requests.get(f"{BASE_URL}/api/inbox", headers=_h(user_b["id_token"]), timeout=15)
        fr_uids = {fr["from_user"]["uid"] for fr in ir.json()["incoming_friend_requests"]}
        assert user_a["uid"] not in fr_uids

        # A's /api/likes shows B as matched + friended.
        lr = requests.get(f"{BASE_URL}/api/likes", headers=_h(user_a["id_token"]), timeout=15)
        b_like = next((l for l in lr.json() if l["player"]["uid"] == user_b["uid"]), None)
        assert b_like is not None
        assert b_like["matched"] is True
        assert b_like["friended"] is True

        # B's /api/likes also shows A matched + friended (B got a like recorded on accept).
        lr2 = requests.get(f"{BASE_URL}/api/likes", headers=_h(user_b["id_token"]), timeout=15)
        a_like = next((l for l in lr2.json() if l["player"]["uid"] == user_a["uid"]), None)
        assert a_like is not None
        assert a_like["matched"] is True
        assert a_like["friended"] is True

    def test_decline_friend_request(self, user_a, user_c):
        # A -> C (fresh pair)
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_c['uid']}",
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200
        # C declines
        dr = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_a['uid']}/decline",
            headers=_h(user_c["id_token"]),
            timeout=15,
        )
        assert dr.status_code == 200
        # Second decline -> 404
        dr2 = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_a['uid']}/decline",
            headers=_h(user_c["id_token"]),
            timeout=15,
        )
        assert dr2.status_code == 404

    def test_send_friend_request_auto_accepts_if_liked(self, user_b, user_c):
        # B likes C first via /api/swipes
        sr = requests.post(
            f"{BASE_URL}/api/swipes",
            json={"target_uid": user_c["uid"], "action": "like"},
            headers=_h(user_b["id_token"]),
            timeout=15,
        )
        assert sr.status_code == 200
        # Now C sends a friend request to B -> should auto-match (reverse like exists)
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_b['uid']}",
            headers=_h(user_c["id_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["matched"] is True

    def test_send_self_friend_request_400(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_a['uid']}",
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 400

    def test_send_friend_request_unknown_uid_404(self, user_a):
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/no-such-uid-xyz",
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 404

    def test_accept_with_no_pending_404(self, user_a, user_c):
        # No outstanding FR from user_c to user_a at this point
        r = requests.post(
            f"{BASE_URL}/api/friend-requests/{user_c['uid']}/accept",
            headers=_h(user_a["id_token"]),
            timeout=15,
        )
        assert r.status_code == 404


# ---------- Inbox auth ----------

class TestInboxAuth:
    def test_inbox_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/inbox", timeout=10)
        assert r.status_code == 401

    def test_inbox_shape(self, user_a):
        r = requests.get(f"{BASE_URL}/api/inbox", headers=_h(user_a["id_token"]), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "incoming_likes" in body
        assert "incoming_friend_requests" in body
        assert isinstance(body["incoming_likes"], list)
        assert isinstance(body["incoming_friend_requests"], list)
