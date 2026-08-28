"""Iteration 26 — Legal compliance features (ledger disclaimer, scorecard
certification checkbox + finalize endpoint, clubhouse fair-play agreement).

Focus:
  1. Schema — LeagueMember has clubhouse_agreed(bool, default False),
     clubhouse_agreed_at(Optional[str]) via GET /api/leagues/{id}/members.
  2. Schema — Scorecard has finalized, certified, certified_by_user_id,
     certified_by_name, certified_at via GET /api/rounds/{id}.
  3. POST /api/scorecards/{id}/finalize with {certified: false} => 400.
  4. POST /api/scorecards/{id}/finalize with {certified: true} => 200 and
     persists finalized=true, certified_by_user_id, certified_at.
  5. PATCH /api/scorecards/{id}/score on a finalized card => 409.
  6. POST /api/leagues/{id}/clubhouse/agree persists flag + GET /api/leagues/{id}
     returns my_clubhouse_agreed=true.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _signup(prefix="u"):
    email = f"TEST_i26_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


@pytest.fixture(scope="module")
def director():
    u = _signup("dir")
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=20)
    assert r.status_code == 200, r.text
    return u


@pytest.fixture(scope="module")
def league(director):
    payload = {
        "name": f"TEST_i26_League_{uuid.uuid4().hex[:6]}",
        "location": "Iteration 26 Park",
        "format": "Singles",
    }
    r = requests.post(
        f"{BASE_URL}/api/leagues", json=payload, headers=_h(director["id_token"]), timeout=20
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def round_with_card(director, league):
    lid = league["id"]
    # find default season
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons",
                     headers=_h(director["id_token"]), timeout=20)
    assert r.status_code == 200
    seasons = r.json()
    assert seasons, "expected default season on league create"
    season_id = seasons[0]["id"]

    # create round
    rd_payload = {"season_id": season_id, "name": "Iter26 Round",
                  "date": "2026-01-15", "holes": 9}
    r = requests.post(f"{BASE_URL}/api/leagues/{lid}/rounds", json=rd_payload,
                      headers=_h(director["id_token"]), timeout=20)
    assert r.status_code == 200, r.text
    rd = r.json()

    # director is a member (auto-added). Find member id.
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/members",
                     headers=_h(director["id_token"]), timeout=20)
    assert r.status_code == 200
    members = r.json()
    assert members
    my_member_id = members[0]["id"]

    # create card
    r = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/cards",
                      json={"label": "A", "player_ids": [my_member_id]},
                      headers=_h(director["id_token"]), timeout=20)
    assert r.status_code == 200, r.text

    # fetch scorecards
    r = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}",
                     headers=_h(director["id_token"]), timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["scorecards"], "expected a scorecard"
    return {"round": rd, "scorecard": data["scorecards"][0], "league_id": lid}


# ---------------- Schema: LeagueMember ----------------
class TestLeagueMemberSchema:
    def test_clubhouse_agreed_defaults_false(self, director, league):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/members",
                         headers=_h(director["id_token"]), timeout=20)
        assert r.status_code == 200
        members = r.json()
        assert members
        m = members[0]
        assert "clubhouse_agreed" in m
        assert m["clubhouse_agreed"] is False
        assert "clubhouse_agreed_at" in m
        assert m["clubhouse_agreed_at"] is None


# ---------------- Schema: Scorecard ----------------
class TestScorecardSchema:
    def test_scorecard_has_cert_fields(self, director, round_with_card):
        sc = round_with_card["scorecard"]
        for key in ("finalized", "certified", "certified_by_user_id",
                    "certified_by_name", "certified_at"):
            assert key in sc, f"Scorecard missing field: {key}"
        assert sc["finalized"] is False
        assert sc["certified"] is False


# ---------------- Finalize enforcement ----------------
class TestFinalizeEnforcement:
    def test_finalize_requires_certified_true(self, director, round_with_card):
        sc = round_with_card["scorecard"]
        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc['id']}/finalize",
            json={"certified": False},
            headers=_h(director["id_token"]),
            timeout=20,
        )
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "Certification required" in detail

    def test_finalize_success_and_persist(self, director, round_with_card):
        sc = round_with_card["scorecard"]
        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc['id']}/finalize",
            json={"certified": True},
            headers=_h(director["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body.get("finalized") is True
        assert body.get("certified_by_user_id") == director["uid"]

        # Verify persistence via GET /api/rounds/{id}
        r2 = requests.get(
            f"{BASE_URL}/api/rounds/{round_with_card['round']['id']}",
            headers=_h(director["id_token"]),
            timeout=20,
        )
        assert r2.status_code == 200
        cards = r2.json()["scorecards"]
        got = next((c for c in cards if c["id"] == sc["id"]), None)
        assert got is not None
        assert got["finalized"] is True
        assert got["certified"] is True
        assert got["certified_by_user_id"] == director["uid"]
        assert got["certified_at"] is not None

    def test_score_edit_blocked_after_finalize(self, director, round_with_card):
        sc = round_with_card["scorecard"]
        r = requests.patch(
            f"{BASE_URL}/api/scorecards/{sc['id']}/score",
            json={"hole": 1, "strokes": 3},
            headers=_h(director["id_token"]),
            timeout=20,
        )
        assert r.status_code == 409, r.text
        assert "already finalized" in r.json().get("detail", "").lower()

    def test_finalize_again_idempotent(self, director, round_with_card):
        sc = round_with_card["scorecard"]
        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc['id']}/finalize",
            json={"certified": True},
            headers=_h(director["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json().get("already_finalized") is True


# ---------------- Clubhouse agreement ----------------
class TestClubhouseAgreement:
    def test_agree_persists_and_get_returns_true(self, director, league):
        lid = league["id"]
        # initial state via /api/leagues/{id}
        r0 = requests.get(f"{BASE_URL}/api/leagues/{lid}",
                          headers=_h(director["id_token"]), timeout=20)
        assert r0.status_code == 200
        assert r0.json().get("my_clubhouse_agreed") is False

        # POST agree
        r = requests.post(f"{BASE_URL}/api/leagues/{lid}/clubhouse/agree",
                          headers=_h(director["id_token"]), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("clubhouse_agreed") is True or body.get("already_agreed") is True

        # GET /api/leagues/{id} shows my_clubhouse_agreed=true
        r2 = requests.get(f"{BASE_URL}/api/leagues/{lid}",
                          headers=_h(director["id_token"]), timeout=20)
        assert r2.status_code == 200
        assert r2.json().get("my_clubhouse_agreed") is True

        # LeagueMember doc reflects it
        r3 = requests.get(f"{BASE_URL}/api/leagues/{lid}/members",
                         headers=_h(director["id_token"]), timeout=20)
        m = r3.json()[0]
        assert m["clubhouse_agreed"] is True
        assert m["clubhouse_agreed_at"] is not None

    def test_agree_idempotent(self, director, league):
        r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/clubhouse/agree",
                          headers=_h(director["id_token"]), timeout=20)
        assert r.status_code == 200
        assert r.json().get("already_agreed") is True


# ---------------- Auth ----------------
class TestAuthGating:
    def test_finalize_requires_auth(self, round_with_card):
        r = requests.post(
            f"{BASE_URL}/api/scorecards/{round_with_card['scorecard']['id']}/finalize",
            json={"certified": True}, timeout=20,
        )
        assert r.status_code == 401

    def test_clubhouse_agree_requires_auth(self, league):
        r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/clubhouse/agree",
                          timeout=20)
        assert r.status_code == 401
