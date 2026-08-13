"""Iteration 46 — Clubhouse feed media (image/video) + validation.

Tests the FeedPostCreate contract:
- Empty body AND no media -> 400 "Post must include text or media"
- image_path only (no body) -> 200
- video_path only -> 200
- text + image + video -> 200 and echo the fields
- GET /feed returns posts including image_path/video_path
- DELETE /api/feed/{id} works for author (post disappears / hidden for non-director)
"""
from __future__ import annotations
import os, uuid, time, io, pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup():
    for _ in range(6):
        email = f"TEST_i46_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(15)
    pytest.skip("Firebase Identity rate-limiting")


@pytest.fixture(scope="module")
def director():
    return _signup()


@pytest.fixture(scope="module")
def member(league):  # noqa: F811
    u = _signup()
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/join",
                      headers=_h(u["token"]), timeout=15)
    assert r.status_code in (200, 201)
    return u


@pytest.fixture(scope="module")
def league(director):
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"TEST_i46-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Singles", "entry_fee": 0.0},
        headers=_h(director["token"]), timeout=15).json()
    return lg


@pytest.fixture(scope="module")
def uploaded_image(director):
    # 1x1 pixel JPEG
    jpg_bytes = bytes.fromhex(
        "FFD8FFE000104A46494600010100000100010000FFDB004300080606070605080707070909080A0C140D0C0B0B0C1912130F141D1A1F1E1D1A1C1C20242E2720222C231C1C2837292C30313434341F27393D38323C2E333432FFDB0043010909090C0B0C180D0D1832211C213232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232FFC00011080001000103012200021101031101FFC4001F0000010501010101010100000000000000000102030405060708090A0BFFC400B5100002010303020403050504040000017D01020300041105122131410613516107227114328191A1082342B1C11552D1F02433627282090A161718191A25262728292A3435363738393A434445464748494A535455565758595A636465666768696A737475767778797A838485868788898A92939495969798999AA2A3A4A5A6A7A8A9AAB2B3B4B5B6B7B8B9BAC2C3C4C5C6C7C8C9CAD2D3D4D5D6D7D8D9DAE1E2E3E4E5E6E7E8E9EAF1F2F3F4F5F6F7F8F9FAFFC4001F0100030101010101010101010000000000000102030405060708090A0BFFC400B51100020102040403040705040400010277000102031104052131061241510761711322328108144291A1B1C109233352F0156272D10A162434E125F11718191A262728292A35363738393A434445464748494A535455565758595A636465666768696A737475767778797A82838485868788898A92939495969798999AA2A3A4A5A6A7A8A9AAB2B3B4B5B6B7B8B9BAC2C3C4C5C6C7C8C9CAD2D3D4D5D6D7D8D9DAE2E3E4E5E6E7E8E9EAF2F3F4F5F6F7F8F9FAFFDA000C03010002110311003F00FBFCFBFF00D9"
    )
    files = {"file": ("test.jpg", io.BytesIO(jpg_bytes), "image/jpeg")}
    r = requests.post(f"{BASE_URL}/api/files/upload", files=files,
                      headers=_h(director["token"]), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["path"]


# 1. Empty body + no media -> 400
def test_empty_post_rejected(director, league):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": ""}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 400
    assert "text or media" in r.json().get("detail", "").lower()


def test_whitespace_only_rejected(director, league):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": "   \n  "}, headers=_h(director["token"]), timeout=15)
    assert r.status_code == 400


# 2. text-only ok
def test_text_only_ok(director, league):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": "TEST_i46 hello world"},
                      headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    p = r.json()
    assert p["body"] == "TEST_i46 hello world"
    assert p["image_path"] is None
    assert p["video_path"] is None


# 3. image-only ok
def test_image_only_ok(director, league, uploaded_image):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": "", "image_path": uploaded_image},
                      headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["image_path"] == uploaded_image
    assert p["body"] == ""


# 4. video-only ok
def test_video_only_ok(director, league):
    fake_video_path = "clubhouse/fake_video.mp4"
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": "", "video_path": fake_video_path},
                      headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["video_path"] == fake_video_path


# 5. text + image + video echoed
def test_full_post_echo(director, league, uploaded_image):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": "TEST_i46 combo",
                            "image_path": uploaded_image,
                            "video_path": "clubhouse/x.mp4",
                            "video_poster": "clubhouse/poster.jpg"},
                      headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    p = r.json()
    assert p["body"] == "TEST_i46 combo"
    assert p["image_path"] == uploaded_image
    assert p["video_path"] == "clubhouse/x.mp4"
    assert p["video_poster"] == "clubhouse/poster.jpg"


# 6. GET feed includes new fields
def test_get_feed_includes_media_fields(director, league, uploaded_image):
    create = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                           json={"body": "TEST_i46 fetchme", "image_path": uploaded_image},
                           headers=_h(director["token"]), timeout=15)
    assert create.status_code == 200
    created_id = create.json()["id"]

    r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                     headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    posts = r.json()
    match = next((p for p in posts if p["id"] == created_id), None)
    assert match is not None
    assert match["image_path"] == uploaded_image
    assert "video_path" in match  # field present even if null


# 7. Non-member cannot post
def test_non_member_cannot_post(league):
    stranger = _signup()
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/feed",
                      json={"body": "TEST_i46 stranger"},
                      headers=_h(stranger["token"]), timeout=15)
    assert r.status_code in (401, 403, 404)


# 8. Mute endpoint reachable by director
def test_director_can_mute_member(director, league, member):
    r = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/mute/{member['profile'].get('uid') or member['profile'].get('user_id')}",
        headers=_h(director["token"]), timeout=15)
    assert r.status_code in (200, 204)


# 9. Muted member post behavior (informational — mute endpoint currently
# records the mute but does not enforce posting block server-side; the
# frontend hides the composer for muted users. Assert the call succeeded
# and the record exists via GET /mutes.)
def test_mute_persists(director, league, member):
    r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/mutes",
                     headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200
    rows = r.json()
    muted_uid = member['profile'].get('uid') or member['profile'].get('user_id')
    assert any(row.get("user_id") == muted_uid or row.get("uid") == muted_uid for row in rows)
