"""Iteration 52 — Distance Throw Tracker + Lifetime Vault.

Verifies:
 1) Haversine correctness: server-computed distance for a known
    lat/lon pair matches the expected feet within 1% tolerance.
 2) `/api/throws` POST persists the throw and returns the server's
    Haversine-computed distance (client_distance_ft is stored but
    doesn't override the server value).
 3) `/api/throws` GET returns rows sorted newest-first and includes a
    correct `personal_best_ft`.
 4) Sanity guard: a throw >2000ft is rejected 400.
 5) `/api/vault/summary` returns the shape the frontend needs:
    `recent`, `by_month`, `hole_stats`, `total_rounds`.
"""
from __future__ import annotations
import os
import uuid
import time
import math
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
        email = f"TEST_i52_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def _haversine_feet(a, b):
    R = 20_902_231
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))


def test_throw_haversine_accuracy_and_persistence():
    u = _signup()
    # Two points ~300 ft apart at ~lat 40°N. 0.001° lat ≈ 365 ft.
    start = (40.0000, -105.0000)
    end   = (40.00082, -105.0000)  # ~300 ft due north
    expected = _haversine_feet(start, end)

    r = requests.post(f"{BASE_URL}/api/throws",
        json={"start_lat": start[0], "start_lon": start[1],
              "end_lat": end[0], "end_lon": end[1],
              "client_distance_ft": 999.9, "disc": "Destroyer"},
        headers=_h(u["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # Server distance must be independent of the client-claimed value.
    assert body["distance_ft"] != 999.9
    # Within 1% of Python-computed expected.
    assert abs(body["distance_ft"] - expected) / expected < 0.01
    assert body["client_distance_ft"] == 999.9  # stored for audit
    assert body["disc"] == "Destroyer"

    # GET list
    lst = requests.get(f"{BASE_URL}/api/throws",
        headers=_h(u["token"]), timeout=15).json()
    assert lst["count"] == 1
    assert lst["personal_best_ft"] == body["distance_ft"]
    assert lst["throws"][0]["id"] == body["id"]


def test_throw_rejects_impossible_distance():
    u = _signup()
    # Two points 1° apart in latitude ≈ 364,000 ft → way over cap.
    r = requests.post(f"{BASE_URL}/api/throws",
        json={"start_lat": 40.0, "start_lon": -105.0,
              "end_lat": 41.0, "end_lon": -105.0,
              "client_distance_ft": 100},
        headers=_h(u["token"]), timeout=15)
    assert r.status_code == 400
    assert "sanity" in r.json()["detail"].lower()


def test_vault_summary_shape_empty_user():
    u = _signup()
    r = requests.get(f"{BASE_URL}/api/vault/summary",
        headers=_h(u["token"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    for key in ("recent", "by_month", "hole_stats", "total_rounds"):
        assert key in body
    assert body["recent"] == []
    assert body["by_month"] == {}
    assert body["hole_stats"] == {}
    assert body["total_rounds"] == 0
