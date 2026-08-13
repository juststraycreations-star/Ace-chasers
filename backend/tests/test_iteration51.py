"""Iteration 51 — Feed post media[] array + backward-compat.

`POST /api/leagues/{id}/feed` now accepts an ordered `media` array
where each item is `{ kind: "image"|"video", path, poster? }`. Legacy
callers that still send `image_path` / `video_path` continue to work —
they are normalized into the media array at write time. First-of-kind
media is also mirrored back to the legacy single-item fields so pre-
iteration-51 clients (mobile/share-cards) still render.
"""
from __future__ import annotations
import os
import uuid
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "")
            .rstrip("/") or "http://localhost:8001")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i51_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def _make_league(tok):
    return requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i51-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Singles", "entry_fee": 0.0},
        headers=_h(tok), timeout=15).json()


def test_feed_post_media_array_full_round_trip():
    d = _signup()
    lg = _make_league(d["token"])
    payload = {
        "body": "multi-media post",
        "media": [
            {"kind": "image", "path": "https://cdn.example/a.jpg"},
            {"kind": "image", "path": "https://cdn.example/b.jpg"},
            {"kind": "video", "path": "https://cdn.example/c.mp4", "poster": "https://cdn.example/c.png"},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/feed",
        json=payload, headers=_h(d["token"]), timeout=15)
    assert r.status_code == 200, r.text
    post = r.json()
    assert len(post["media"]) == 3
    assert [m["kind"] for m in post["media"]] == ["image", "image", "video"]
    # Legacy mirror fields must carry the first-of-kind so pre-iter-51 clients still work.
    assert post["image_path"] == "https://cdn.example/a.jpg"
    assert post["video_path"] == "https://cdn.example/c.mp4"
    assert post["video_poster"] == "https://cdn.example/c.png"

    # Feed GET returns the same shape.
    feed = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/feed",
        headers=_h(d["token"]), timeout=15).json()
    posted = next((p for p in feed if p["id"] == post["id"]), None)
    assert posted is not None
    assert len(posted["media"]) == 3


def test_legacy_image_path_still_accepted_and_normalized():
    d = _signup()
    lg = _make_league(d["token"])
    # Legacy caller: send image_path / video_path — no `media` field.
    payload = {"body": "legacy client", "image_path": "https://cdn.example/legacy.jpg"}
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/feed",
        json=payload, headers=_h(d["token"]), timeout=15)
    assert r.status_code == 200, r.text
    post = r.json()
    # Server normalizes legacy fields into `media` so new-shape clients still render.
    assert len(post["media"]) == 1
    assert post["media"][0]["kind"] == "image"
    assert post["media"][0]["path"] == "https://cdn.example/legacy.jpg"
    assert post["image_path"] == "https://cdn.example/legacy.jpg"


def test_empty_body_and_empty_media_rejected():
    d = _signup()
    lg = _make_league(d["token"])
    r = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/feed",
        json={"body": "", "media": []}, headers=_h(d["token"]), timeout=15)
    assert r.status_code == 400
    assert "text or media" in r.json().get("detail", "").lower()
