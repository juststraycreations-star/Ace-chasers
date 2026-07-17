"""Iteration 27 — Backend tests for:
 1. P0 fix: _upsert_league_user coerces email=None to '' (no 500 on
    /api/leagues* for pathological users). New signup can create a league
    end-to-end.
 2. Sweep-Finalize round endpoint POST /api/rounds/{id}/finalize.
 3. DM Terms endpoints (GET /api/users/me exposes dmTermsAgreedAt;
    POST /api/users/me/dm-terms/agree persists + idempotent).
 4. Clubhouse endpoints post-refactor (announcements/lost-found/stories/feed).
 5. Regression: individual scorecard finalize + PATCH 409 guard still works.
 6. Regression: /api/discovery, /api/feed, /api/courses, /api/users/me
    /api/messages/threads still respond for authenticated users.
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
    email = f"TEST_i27_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=25,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _sync(u):
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=25)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def director():
    u = _signup("dir")
    _sync(u)
    return u


@pytest.fixture(scope="module")
def member():
    u = _signup("mem")
    _sync(u)
    return u


@pytest.fixture(scope="module")
def league(director):
    payload = {
        "name": f"TEST_i27_League_{uuid.uuid4().hex[:6]}",
        "location": "Iter 27 Park",
        "format": "Singles",
    }
    r = requests.post(f"{BASE_URL}/api/leagues", json=payload,
                      headers=_h(director["id_token"]), timeout=25)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def round_with_cards(director, league):
    lid = league["id"]
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons",
                     headers=_h(director["id_token"]), timeout=25)
    assert r.status_code == 200
    season_id = r.json()[0]["id"]

    r = requests.post(
        f"{BASE_URL}/api/leagues/{lid}/rounds",
        json={"season_id": season_id, "name": "Iter27 Round", "date": "2026-01-20", "holes": 9},
        headers=_h(director["id_token"]), timeout=25,
    )
    assert r.status_code == 200, r.text
    rd = r.json()

    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/members",
                     headers=_h(director["id_token"]), timeout=25)
    members = r.json()
    my_member_id = members[0]["id"]

    # Create 2 cards
    for lbl in ("A", "B"):
        r = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/cards",
                          json={"label": lbl, "player_ids": [my_member_id]},
                          headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 200, r.text

    r = requests.get(f"{BASE_URL}/api/rounds/{rd['id']}",
                     headers=_h(director["id_token"]), timeout=25)
    return {"round": rd, "scorecards": r.json()["scorecards"], "league_id": lid}


# ---------- P0 FIX: create league by fresh user ----------
class TestCreateLeagueP0Fix:
    def test_fresh_signup_can_create_league_no_500(self):
        u = _signup("p0")
        _sync(u)
        r = requests.post(
            f"{BASE_URL}/api/leagues",
            json={"name": f"TEST_i27_P0_{uuid.uuid4().hex[:6]}", "location": "Loc", "format": "Singles"},
            headers=_h(u["id_token"]),
            timeout=25,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("id")

    def test_users_me_survives_email_field_edge(self):
        u = _signup("me")
        _sync(u)
        r = requests.get(f"{BASE_URL}/api/users/me", headers=_h(u["id_token"]), timeout=25)
        assert r.status_code == 200, r.text
        data = r.json()
        # dmTermsAgreedAt field exists in response (may be null)
        assert "dmTermsAgreedAt" in data


# ---------- SWEEP FINALIZE ----------
class TestSweepFinalize:
    def test_requires_certified_true(self, director, round_with_cards):
        rid = round_with_cards["round"]["id"]
        r = requests.post(
            f"{BASE_URL}/api/rounds/{rid}/finalize",
            json={"certified": False, "complete_round": False},
            headers=_h(director["id_token"]), timeout=25,
        )
        assert r.status_code == 400, r.text
        assert "Certification required" in r.json().get("detail", "")

    def test_non_director_forbidden(self, round_with_cards):
        # Fresh non-member user
        u = _signup("nom")
        _sync(u)
        rid = round_with_cards["round"]["id"]
        r = requests.post(
            f"{BASE_URL}/api/rounds/{rid}/finalize",
            json={"certified": True, "complete_round": False},
            headers=_h(u["id_token"]), timeout=25,
        )
        assert r.status_code in (403, 404), r.text  # 404 if not member; 403 if member

    def test_success_certifies_all(self, director, round_with_cards):
        rid = round_with_cards["round"]["id"]
        sc_ids = [sc["id"] for sc in round_with_cards["scorecards"]]
        r = requests.post(
            f"{BASE_URL}/api/rounds/{rid}/finalize",
            json={"certified": True, "complete_round": True},
            headers=_h(director["id_token"]), timeout=25,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert set(body["certified_scorecard_ids"]) == set(sc_ids)
        assert body["round_status"] == "completed"

        # Verify persistence + names contain DIRECTOR SWEEP
        r2 = requests.get(f"{BASE_URL}/api/rounds/{rid}",
                          headers=_h(director["id_token"]), timeout=25)
        cards = r2.json()["scorecards"]
        for c in cards:
            assert c["finalized"] is True
            assert c["certified"] is True
            assert c["certified_by_user_id"] == director["uid"]
            assert "DIRECTOR SWEEP" in (c.get("certified_by_name") or "")

    def test_empty_round_sweep_returns_200(self, director, league):
        # Create a fresh round with zero cards
        lid = league["id"]
        r = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons",
                         headers=_h(director["id_token"]), timeout=25)
        season_id = r.json()[0]["id"]
        r = requests.post(
            f"{BASE_URL}/api/leagues/{lid}/rounds",
            json={"season_id": season_id, "name": "Empty Round", "date": "2026-01-21", "holes": 9},
            headers=_h(director["id_token"]), timeout=25,
        )
        empty_rid = r.json()["id"]
        r = requests.post(
            f"{BASE_URL}/api/rounds/{empty_rid}/finalize",
            json={"certified": True, "complete_round": False},
            headers=_h(director["id_token"]), timeout=25,
        )
        assert r.status_code == 200, r.text
        assert r.json()["certified_scorecard_ids"] == []


# ---------- DM TERMS ----------
class TestDmTerms:
    def test_dm_terms_field_null_initially(self):
        u = _signup("dm1")
        _sync(u)
        r = requests.get(f"{BASE_URL}/api/users/me", headers=_h(u["id_token"]), timeout=25)
        assert r.status_code == 200
        assert "dmTermsAgreedAt" in r.json()
        assert r.json()["dmTermsAgreedAt"] is None

    def test_agree_sets_timestamp(self):
        u = _signup("dm2")
        _sync(u)
        r = requests.post(f"{BASE_URL}/api/users/me/dm-terms/agree",
                          headers=_h(u["id_token"]), timeout=25)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("dmTermsAgreedAt") is not None
        ts1 = body["dmTermsAgreedAt"]

        # Idempotent
        r2 = requests.post(f"{BASE_URL}/api/users/me/dm-terms/agree",
                           headers=_h(u["id_token"]), timeout=25)
        assert r2.status_code == 200
        assert r2.json()["dmTermsAgreedAt"] == ts1  # unchanged

    def test_agree_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/users/me/dm-terms/agree", timeout=25)
        assert r.status_code == 401


# ---------- CLUBHOUSE ENDPOINTS POST-REFACTOR ----------
class TestClubhouseRefactor:
    def test_announcements_crud(self, director, league):
        lid = league["id"]
        r = requests.post(
            f"{BASE_URL}/api/leagues/{lid}/announcements",
            json={"title": "TEST_i27 Ann", "body": "hello", "urgent": False},
            headers=_h(director["id_token"]), timeout=25,
        )
        assert r.status_code == 200, r.text
        ann_id = r.json()["id"]

        r2 = requests.get(f"{BASE_URL}/api/leagues/{lid}/announcements",
                          headers=_h(director["id_token"]), timeout=25)
        assert r2.status_code == 200
        assert any(a["id"] == ann_id for a in r2.json())

        r3 = requests.delete(f"{BASE_URL}/api/announcements/{ann_id}",
                              headers=_h(director["id_token"]), timeout=25)
        assert r3.status_code == 200

    def test_lost_found_crud(self, director, league):
        lid = league["id"]
        r = requests.post(f"{BASE_URL}/api/leagues/{lid}/lost-found",
                          json={"title": "TEST lost disc", "description": "yellow"},
                          headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 200
        item_id = r.json()["id"]

        r2 = requests.get(f"{BASE_URL}/api/leagues/{lid}/lost-found",
                          headers=_h(director["id_token"]), timeout=25)
        assert r2.status_code == 200
        assert any(i["id"] == item_id for i in r2.json())

        r3 = requests.patch(f"{BASE_URL}/api/lost-found/{item_id}/resolve",
                            headers=_h(director["id_token"]), timeout=25)
        assert r3.status_code == 200

    def test_stories_endpoint(self, director, league):
        lid = league["id"]
        r = requests.post(f"{BASE_URL}/api/leagues/{lid}/stories",
                          json={"image_path": "https://res.cloudinary.com/test/x.jpg", "caption": "test"},
                          headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 200
        r2 = requests.get(f"{BASE_URL}/api/leagues/{lid}/stories",
                          headers=_h(director["id_token"]), timeout=25)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)
        assert len(r2.json()) >= 1

    def test_feed_endpoints(self, director, league):
        lid = league["id"]
        r = requests.post(f"{BASE_URL}/api/leagues/{lid}/feed",
                          json={"title": "TEST feed", "body": "hello"},
                          headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 200
        r2 = requests.get(f"{BASE_URL}/api/leagues/{lid}/feed",
                          headers=_h(director["id_token"]), timeout=25)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)


# ---------- REGRESSION: individual finalize + core flows ----------
class TestRegression:
    def test_core_endpoints_ok(self, director):
        for path in ("/api/discovery", "/api/feed", "/api/courses",
                     "/api/users/me", "/api/messages/threads"):
            r = requests.get(f"{BASE_URL}{path}", headers=_h(director["id_token"]), timeout=25)
            assert r.status_code == 200, f"{path} => {r.status_code} {r.text[:200]}"

    def test_scorecard_finalize_still_works(self, director, league):
        # Fresh round + card for individual finalize
        lid = league["id"]
        r = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons",
                         headers=_h(director["id_token"]), timeout=25)
        season_id = r.json()[0]["id"]
        r = requests.post(f"{BASE_URL}/api/leagues/{lid}/rounds",
                          json={"season_id": season_id, "name": "IndivFinal", "date": "2026-01-22", "holes": 9},
                          headers=_h(director["id_token"]), timeout=25)
        rid = r.json()["id"]
        r = requests.get(f"{BASE_URL}/api/leagues/{lid}/members",
                         headers=_h(director["id_token"]), timeout=25)
        mid = r.json()[0]["id"]
        r = requests.post(f"{BASE_URL}/api/rounds/{rid}/cards",
                          json={"label": "X", "player_ids": [mid]},
                          headers=_h(director["id_token"]), timeout=25)
        r = requests.get(f"{BASE_URL}/api/rounds/{rid}",
                         headers=_h(director["id_token"]), timeout=25)
        sc_id = r.json()["scorecards"][0]["id"]

        # Reject without certification
        r = requests.post(f"{BASE_URL}/api/scorecards/{sc_id}/finalize",
                          json={"certified": False}, headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 400

        # Success with certification
        r = requests.post(f"{BASE_URL}/api/scorecards/{sc_id}/finalize",
                          json={"certified": True}, headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 200

        # PATCH after finalize => 409
        r = requests.patch(f"{BASE_URL}/api/scorecards/{sc_id}/score",
                           json={"hole": 1, "strokes": 3},
                           headers=_h(director["id_token"]), timeout=25)
        assert r.status_code == 409
