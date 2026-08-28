"""Iteration 49 — Winner name stamped on completed rounds.

`_finalize_round` now writes `winner_id` + `winner_name` back to the
round document so the League Dashboard Completed Archive can render a
"Winner · <name>" chip without an extra client-side lookup.
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
        email = f"TEST_i49_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_completed_round_carries_winner_name_and_id():
    d = _signup()
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i49-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Singles", "entry_fee": 0.0},
        headers=_h(d["token"]), timeout=15).json()
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(d["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "Winner-Stamp", "date": "2026-09-01",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(d["token"]), timeout=15).json()
    # Activate & join to spawn a scorecard for the director
    requests.patch(f"{BASE_URL}/api/rounds/{rd['id']}/status",
        json={"status": "active"}, headers=_h(d["token"]), timeout=15)
    j = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join",
        headers=_h(d["token"]), timeout=15).json()
    sc_id = j["scorecard"]["id"]
    # Log 9 pars → total 27
    for hole in range(1, 10):
        requests.patch(f"{BASE_URL}/api/scorecards/{sc_id}/score",
            json={"hole": hole, "strokes": 3}, headers=_h(d["token"]), timeout=15)
    # Certify & finalize
    requests.post(f"{BASE_URL}/api/scorecards/{sc_id}/finalize",
        json={"certified": True}, headers=_h(d["token"]), timeout=15)
    # Trigger round finalize (sweep) — completed status stamps winner
    requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/finalize",
        json={"certified": True}, headers=_h(d["token"]), timeout=15)

    # Fetch the rounds list — the completed round MUST carry winner_name.
    rounds = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        headers=_h(d["token"]), timeout=15).json()
    r = next((x for x in rounds if x["id"] == rd["id"]), None)
    assert r is not None
    assert r.get("status") == "completed"
    # Director has display name from Firebase; winner_name should not be empty
    winner_name = r.get("winner_name")
    winner_id = r.get("winner_id")
    assert winner_name and isinstance(winner_name, str) and winner_name.strip()
    assert winner_id and isinstance(winner_id, str)
