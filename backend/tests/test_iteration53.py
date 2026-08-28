"""Iteration 53 — Distance Throw Tracker offline-queue hardening.

Verifies the server-side idempotency contract that backs the client's
retry-with-backoff sync loop. If the client retries a POST /api/throws
with the same `Idempotency-Key` header, the server must:
  1) return 200 with the same throw doc (not 4xx, not a fresh insert),
  2) not double-insert the row.
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
        email = f"TEST_i53_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_throw_idempotency_key_dedupes_replay():
    """POSTing the same throw twice with the same Idempotency-Key must
    return the same throw doc and produce only one row in the list."""
    u = _signup()
    idem = f"throw-{uuid.uuid4().hex}"
    payload = {
        "start_lat": 40.0, "start_lon": -105.0,
        "end_lat": 40.00082, "end_lon": -105.0,
        "client_distance_ft": 300, "disc": "Buzzz",
    }
    headers = {**_h(u["token"]), "Idempotency-Key": idem}
    r1 = requests.post(f"{BASE_URL}/api/throws", json=payload, headers=headers, timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{BASE_URL}/api/throws", json=payload, headers=headers, timeout=15)
    assert r2.status_code == 200, r2.text
    # Same throw doc returned — same id, same distance.
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["distance_ft"] == r2.json()["distance_ft"]
    # Exactly one throw persisted for this user.
    lst = requests.get(f"{BASE_URL}/api/throws", headers=_h(u["token"]), timeout=15).json()
    assert lst["count"] == 1


def test_throw_without_idempotency_key_creates_two_rows():
    """Regression guard: no Idempotency-Key means dedupe is off, so two
    identical POSTs must produce two distinct rows."""
    u = _signup()
    payload = {
        "start_lat": 40.0, "start_lon": -105.0,
        "end_lat": 40.00082, "end_lon": -105.0,
        "client_distance_ft": 300,
    }
    r1 = requests.post(f"{BASE_URL}/api/throws", json=payload, headers=_h(u["token"]), timeout=15)
    r2 = requests.post(f"{BASE_URL}/api/throws", json=payload, headers=_h(u["token"]), timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"]
    lst = requests.get(f"{BASE_URL}/api/throws", headers=_h(u["token"]), timeout=15).json()
    assert lst["count"] == 2


def test_throw_idempotency_key_scoped_to_user():
    """Two different users using the same Idempotency-Key value must each
    get their own throw. The key is scoped by user_id server-side."""
    u1 = _signup()
    u2 = _signup()
    idem = f"shared-{uuid.uuid4().hex}"
    payload = {
        "start_lat": 40.0, "start_lon": -105.0,
        "end_lat": 40.00082, "end_lon": -105.0,
        "client_distance_ft": 300,
    }
    r1 = requests.post(f"{BASE_URL}/api/throws", json=payload,
                        headers={**_h(u1["token"]), "Idempotency-Key": idem}, timeout=15)
    r2 = requests.post(f"{BASE_URL}/api/throws", json=payload,
                        headers={**_h(u2["token"]), "Idempotency-Key": idem}, timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200
    # Different users, different rows, even with the same key.
    assert r1.json()["id"] != r2.json()["id"]
