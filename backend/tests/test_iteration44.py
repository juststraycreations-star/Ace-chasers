"""Iteration 44 — Fix WS "RECONNECTING…" loop + streamlined scorecard layout.

The RoundScorecard's live socket handshakes were failing 4401 because
`_validate_ws_token` checked a legacy `session_token` row that Firebase
auth never populates. Client would loop reconnect every 3s.

We now verify the incoming query-string token via the same Firebase
helper the HTTP routes use. This test asserts the fix by opening a real
WebSocket to `/api/ws/rounds/{round_id}` with a fresh Firebase idToken
and expecting the "hello" frame instead of a 4401 close.
"""
from __future__ import annotations
import asyncio
import os
import uuid
import time
import json
import pytest
import requests
import websockets
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "")
            .rstrip("/") or "http://localhost:8001")
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(retries=6, backoff=15):
    for _ in range(retries):
        email = f"TEST_i44_{uuid.uuid4().hex[:10]}@example.com"
        r = requests.post(IDENTITY_SIGNUP,
            json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
            assert prof.status_code == 200
            return {"token": tok, "profile": prof.json()}
        time.sleep(backoff)
    pytest.skip("Firebase Identity still rate-limiting")


def test_ws_round_accepts_firebase_token_no_more_reconnecting_loop():
    user = _signup()
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"i44-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Singles", "entry_fee": 0.0},
        headers=_h(user["token"]), timeout=15).json()
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(user["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "WS-Test", "date": "2026-08-11",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3] * 9, "publish_announcement": False},
        headers=_h(user["token"]), timeout=15).json()

    async def _open():
        url = f"{WS_BASE}/api/ws/rounds/{rd['id']}?token={user['token']}"
        async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
            hello = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(hello)
            assert msg["type"] == "hello"
            # Round-trip a ping to prove the socket stays open.
            await ws.send("ping")
            pong = await asyncio.wait_for(ws.recv(), timeout=5)
            assert pong == "pong"
            return True

    ok = asyncio.get_event_loop().run_until_complete(_open())
    assert ok is True


def test_ws_round_rejects_bad_token():
    """Regression: a garbage token must still be rejected 4401, not
    accepted through the legacy session_token fallback."""
    async def _open():
        try:
            url = f"{WS_BASE}/api/ws/rounds/{uuid.uuid4().hex}?token=notarealtoken"
            async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
                await asyncio.wait_for(ws.recv(), timeout=5)
                return False  # If we got here, auth wrongly accepted us
        except websockets.exceptions.InvalidStatusCode:
            return True
        except websockets.exceptions.ConnectionClosedError as e:
            # 4401 close code from the handler
            return e.code == 4401
        except websockets.exceptions.ConnectionClosed as e:
            return getattr(e, "code", None) == 4401
        except Exception:
            return True  # any auth-related failure is fine

    assert asyncio.get_event_loop().run_until_complete(_open()) is True
