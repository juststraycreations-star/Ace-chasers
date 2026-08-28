"""Iteration 41 — Phase-4 CSV consolidation + Handicap chip endpoint.

Verifies:
 1) `GET /api/leagues/{id}/standings.csv` still resolves under the same
    URL after being moved out of `leagues_router.py` into
    `leagues_rounds_router.py`, and its CSV body still lists the
    Handicap column so client hooks / spreadsheets don't break.
 2) `GET /api/leagues/{id}/handicaps` returns the shape SeedManagementPanel
    consumes for its Handicap Preview Chips (`member_id`, `handicap`,
    `rounds_played`).
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

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i41_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_standings_csv_moved_and_handicaps_shape():
    director = _signup()

    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i41-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Match Play", "entry_fee": 0.0},
        headers=_h(director["token"]), timeout=15).json()

    # (1) standings.csv — same URL, still 200, still content-type text/csv,
    # still includes the Handicap column header.
    r = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/standings.csv",
        headers=_h(director["token"]), timeout=15)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("text/csv"), r.headers
    csv_body = r.text
    header_line = csv_body.splitlines()[0]
    assert "Handicap" in header_line
    assert "Player Rating" in header_line
    assert "Bag Tag" in header_line

    # (2) /handicaps shape for the Handicap Preview Chips.
    hc = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/handicaps",
        headers=_h(director["token"]), timeout=15)
    assert hc.status_code == 200
    rows = hc.json()
    assert isinstance(rows, list) and len(rows) >= 1
    row = rows[0]
    for key in ("member_id", "name", "handicap", "rounds_played"):
        assert key in row, f"missing {key} in {row}"
    # Unrated founder → handicap 0, rounds_played 0 (chip renders "—")
    assert row["rounds_played"] == 0
