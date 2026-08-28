"""Iteration 45 — Regression pass for every endpoint RoundScorecard.jsx calls.

Verifies the WS auth refactor didn't break any HTTP routes.
"""
from __future__ import annotations
import os, uuid, time, pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def user():
    for _ in range(6):
        email = f"TEST_i45_{uuid.uuid4().hex[:10]}@example.com"
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
def league_round(user):
    lg = requests.post(f"{BASE_URL}/api/leagues",
        json={"name": f"TEST_i45-{uuid.uuid4().hex[:6]}", "location": "T",
              "format": "Singles", "entry_fee": 0.0},
        headers=_h(user["token"]), timeout=15).json()
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lg['id']}/seasons",
        headers=_h(user["token"]), timeout=15).json()
    rd = requests.post(f"{BASE_URL}/api/leagues/{lg['id']}/rounds",
        json={"name": "RegressionRound", "date": "2026-08-11",
              "season_id": seasons[0]["id"], "holes": 9,
              "par_per_hole": [3]*9, "publish_announcement": False},
        headers=_h(user["token"]), timeout=15).json()
    return {"league": lg, "round": rd}


def test_get_round(user, league_round):
    r = requests.get(f"{BASE_URL}/api/rounds/{league_round['round']['id']}",
                     headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["round"]["id"] == league_round["round"]["id"]


def test_get_round_chat(user, league_round):
    r = requests.get(f"{BASE_URL}/api/rounds/{league_round['round']['id']}/chat",
                     headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_league_members(user, league_round):
    r = requests.get(f"{BASE_URL}/api/leagues/{league_round['league']['id']}/members",
                     headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_join_round(user, league_round):
    r = requests.post(f"{BASE_URL}/api/rounds/{league_round['round']['id']}/join",
                      json={}, headers=_h(user["token"]), timeout=15)
    assert r.status_code in (200, 201, 409)  # 409 if already joined via director


def test_create_card(user, league_round):
    # director should be able to build a card containing themself
    uid = user["profile"]["uid"]
    r = requests.post(f"{BASE_URL}/api/rounds/{league_round['round']['id']}/cards",
                      json={"label": "TEST_Card_A", "player_ids": [uid]},
                      headers=_h(user["token"]), timeout=15)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert "id" in data
    # Save scorecard ids for later
    league_round["card"] = data


def test_patch_scorecard_score(user, league_round):
    card = league_round.get("card")
    if not card:
        pytest.skip("card not created")
    sc_id = card["scorecards"][0]["id"] if "scorecards" in card and card["scorecards"] else None
    # fallback: fetch round to get scorecards
    if not sc_id:
        rd = requests.get(f"{BASE_URL}/api/rounds/{league_round['round']['id']}",
                          headers=_h(user["token"]), timeout=15).json()
        scs = rd.get("scorecards", [])
        assert scs, "no scorecards found"
        sc_id = scs[0]["id"]
    r = requests.patch(f"{BASE_URL}/api/scorecards/{sc_id}/score",
                       json={"hole": 1, "strokes": 3},
                       headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200, r.text
    league_round["sc_id"] = sc_id


def test_auto_pair(user, league_round):
    r = requests.post(f"{BASE_URL}/api/rounds/{league_round['round']['id']}/auto-pair",
                      json={}, headers=_h(user["token"]), timeout=15)
    # auto-pair may 200 or 400 (insufficient players); we just want no 500
    assert r.status_code < 500, r.text
