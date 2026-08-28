"""Iteration 69 — Push notification token registry.

Verifies:
  1) `POST /api/push/register-token` upserts on the token string so
     repeat registrations from the same device don't duplicate rows.
  2) Rejects empty/too-short tokens with 400.
  3) `GET /api/push/tokens` returns only the caller's own rows.
  4) `POST /api/push/unregister-token` removes a caller's row and is
     idempotent (a second call returns deleted=0, not an error).
  5) A caller cannot unregister a token they don't own.
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
        email = f"TEST_i69_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_register_token_and_list_it():
    user = _signup()
    fcm_token = f"fcm-fake-{uuid.uuid4().hex}"
    r = requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": fcm_token, "platform": "android",
              "device_name": "Pixel 8"},
        headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200, r.text

    listing = requests.get(f"{BASE_URL}/api/push/tokens",
                            headers=_h(user["token"]), timeout=15).json()
    assert listing["count"] == 1
    row = listing["tokens"][0]
    assert row["token"] == fcm_token
    assert row["platform"] == "android"
    assert row["device_name"] == "Pixel 8"


def test_register_token_is_upsert_on_token_string():
    """Re-registering the same token twice (Capacitor fires this on
    every cold start) must NOT create a second row."""
    user = _signup()
    fcm_token = f"fcm-fake-{uuid.uuid4().hex}"
    r1 = requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": fcm_token, "platform": "android"},
        headers=_h(user["token"]), timeout=15)
    r2 = requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": fcm_token, "platform": "android",
              "device_name": "Renamed"},
        headers=_h(user["token"]), timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200
    listing = requests.get(f"{BASE_URL}/api/push/tokens",
                            headers=_h(user["token"]), timeout=15).json()
    assert listing["count"] == 1
    # Upsert also updates metadata fields.
    assert listing["tokens"][0]["device_name"] == "Renamed"


def test_empty_token_is_rejected():
    user = _signup()
    r = requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": "", "platform": "android"},
        headers=_h(user["token"]), timeout=15)
    assert r.status_code == 400


def test_listing_is_scoped_to_caller():
    """User A's tokens must never appear in user B's listing."""
    ua = _signup()
    ub = _signup()
    t_a = f"fcm-A-{uuid.uuid4().hex}"
    t_b = f"fcm-B-{uuid.uuid4().hex}"
    requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": t_a, "platform": "android"},
        headers=_h(ua["token"]), timeout=15)
    requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": t_b, "platform": "android"},
        headers=_h(ub["token"]), timeout=15)
    la = requests.get(f"{BASE_URL}/api/push/tokens",
                      headers=_h(ua["token"]), timeout=15).json()
    lb = requests.get(f"{BASE_URL}/api/push/tokens",
                      headers=_h(ub["token"]), timeout=15).json()
    a_tokens = {r["token"] for r in la["tokens"]}
    b_tokens = {r["token"] for r in lb["tokens"]}
    assert t_a in a_tokens and t_b not in a_tokens
    assert t_b in b_tokens and t_a not in b_tokens


def test_unregister_is_idempotent_and_scoped():
    user = _signup()
    fcm_token = f"fcm-fake-{uuid.uuid4().hex}"
    requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": fcm_token, "platform": "android"},
        headers=_h(user["token"]), timeout=15)

    r1 = requests.post(f"{BASE_URL}/api/push/unregister-token",
        json={"token": fcm_token},
        headers=_h(user["token"]), timeout=15)
    assert r1.status_code == 200
    assert r1.json()["deleted"] == 1

    # Second call is a no-op, not an error.
    r2 = requests.post(f"{BASE_URL}/api/push/unregister-token",
        json={"token": fcm_token},
        headers=_h(user["token"]), timeout=15)
    assert r2.status_code == 200
    assert r2.json()["deleted"] == 0

    # A different user cannot delete someone else's token.
    attacker = _signup()
    other = _signup()
    stranger_token = f"fcm-stranger-{uuid.uuid4().hex}"
    requests.post(f"{BASE_URL}/api/push/register-token",
        json={"token": stranger_token, "platform": "android"},
        headers=_h(other["token"]), timeout=15)
    r3 = requests.post(f"{BASE_URL}/api/push/unregister-token",
        json={"token": stranger_token},
        headers=_h(attacker["token"]), timeout=15)
    assert r3.status_code == 200
    assert r3.json()["deleted"] == 0
    # Original owner's row is still there.
    li = requests.get(f"{BASE_URL}/api/push/tokens",
                      headers=_h(other["token"]), timeout=15).json()
    assert any(row["token"] == stranger_token for row in li["tokens"])
