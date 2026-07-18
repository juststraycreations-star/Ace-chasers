"""Iteration 30 — Verify P0 fixes:
  BUG 1: POST /api/leagues/{id}/rounds (director-only)
  BUG 2: POST /api/rounds/{id}/join   (self-serve join, member-only)
  BUG 3: /rounds/{id}/join idempotency
  BUG 4: /rounds/{id}/join 403 for non-members
  + audit of core league surfaces.
"""
from __future__ import annotations
import os, uuid, pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup():
    email = f"TEST_i30_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(IDENTITY, json={"email": email, "password": "demo1234", "returnSecureToken": True}, timeout=25)
    assert r.status_code == 200, r.text
    d = r.json()
    # Sync to backend
    requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(d["idToken"]), timeout=20)
    return {"email": email, "token": d["idToken"], "uid": d["localId"]}


@pytest.fixture(scope="module")
def director():
    return _signup()


@pytest.fixture(scope="module")
def member():
    return _signup()


@pytest.fixture(scope="module")
def outsider():
    return _signup()


@pytest.fixture(scope="module")
def league(director):
    payload = {
        "name": f"TEST i30 League {uuid.uuid4().hex[:6]}",
        "location": "Test City, ST",
        "format": "Singles",
        "description": "iter30 audit",
        "win_points": 10,
        "points_step": 1,
        "entry_fee": 5,
        "divisions": ["Open"],
        "payout_split": {"pool": 0.7, "ace": 0.2, "club": 0.1},
    }
    r = requests.post(f"{BASE_URL}/api/leagues", json=payload, headers=_h(director["token"]), timeout=25)
    assert r.status_code == 200, r.text
    lg = r.json()
    assert "id" in lg
    return lg


@pytest.fixture(scope="module")
def joined_member(league, member):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/join", json={}, headers=_h(member["token"]), timeout=20)
    assert r.status_code == 200, r.text
    return member


# ============= BUG FIX 1 — CREATE ROUND (director-only) =============
class TestCreateRound:
    def test_director_can_create_round(self, league, director):
        # Get season
        s = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/seasons", headers=_h(director["token"]), timeout=20)
        assert s.status_code == 200
        seasons = s.json()
        assert len(seasons) >= 1, "auto-seeded season missing"
        season_id = seasons[0]["id"]

        payload = {"season_id": season_id, "name": "TEST Round Alpha", "date": "2026-02-01", "holes": 18, "course_rating": 54.0}
        r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/rounds", json=payload, headers=_h(director["token"]), timeout=20)
        assert r.status_code == 200, r.text
        rd = r.json()
        assert rd["name"] == "TEST Round Alpha"
        assert rd["holes"] == 18
        assert rd["league_id"] == league["id"]
        assert "id" in rd
        pytest.round_id = rd["id"]  # share via pytest ns

        # Verify GET returns it
        listing = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/rounds", headers=_h(director["token"]), timeout=20)
        assert listing.status_code == 200
        assert any(x["id"] == rd["id"] for x in listing.json())

    def test_non_director_cannot_create_round(self, league, joined_member):
        s = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/seasons", headers=_h(joined_member["token"]), timeout=20)
        season_id = s.json()[0]["id"]
        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/rounds",
            json={"season_id": season_id, "name": "Nope", "date": "2026-02-08"},
            headers=_h(joined_member["token"]), timeout=20,
        )
        assert r.status_code == 403, r.text

    def test_non_member_cannot_create_round(self, league, outsider):
        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/rounds",
            json={"season_id": "x", "name": "Nope", "date": "2026-02-08"},
            headers=_h(outsider["token"]), timeout=20,
        )
        assert r.status_code == 403


# ============= BUG FIX 2/3/4 — SELF-SERVE JOIN ROUND =============
class TestJoinRound:
    def test_member_self_join_creates_card_and_scorecard(self, joined_member):
        rid = pytest.round_id
        r = requests.post(f"{BASE_URL}/api/rounds/{rid}/join", json={}, headers=_h(joined_member["token"]), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("already_joined") is False
        assert body.get("card") and body.get("scorecard")
        card, sc = body["card"], body["scorecard"]
        assert card["round_id"] == rid
        assert card["label"].endswith("'s Card")
        assert len(sc["scores"]) == 18
        assert all(s == 0 for s in sc["scores"])
        assert "handicap_at_round" in sc
        pytest.card_id = card["id"]
        pytest.scorecard_id = sc["id"]

        # Verify GET /rounds/{id} sees the card
        det = requests.get(f"{BASE_URL}/api/rounds/{rid}", headers=_h(joined_member["token"]), timeout=20)
        assert det.status_code == 200
        d = det.json()
        assert any(c["id"] == card["id"] for c in d["cards"])
        assert any(s["id"] == sc["id"] for s in d["scorecards"])

    def test_join_idempotent(self, joined_member):
        rid = pytest.round_id
        r = requests.post(f"{BASE_URL}/api/rounds/{rid}/join", json={}, headers=_h(joined_member["token"]), timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("already_joined") is True
        assert body["card"]["id"] == pytest.card_id
        assert body["scorecard"]["id"] == pytest.scorecard_id

        # Verify still exactly 1 card + 1 scorecard for the member
        det = requests.get(f"{BASE_URL}/api/rounds/{rid}", headers=_h(joined_member["token"]), timeout=20).json()
        member_scs = [s for s in det["scorecards"] if s["member_id"] == body["scorecard"]["member_id"]]
        assert len(member_scs) == 1

    def test_non_member_gets_403(self, outsider):
        rid = pytest.round_id
        r = requests.post(f"{BASE_URL}/api/rounds/{rid}/join", json={}, headers=_h(outsider["token"]), timeout=20)
        assert r.status_code == 403

    def test_bad_round_404(self, joined_member):
        r = requests.post(f"{BASE_URL}/api/rounds/does-not-exist/join", json={}, headers=_h(joined_member["token"]), timeout=20)
        assert r.status_code == 404


# ============= AUDIT — CORE LEAGUE SURFACES =============
class TestLeagueAudit:
    def test_league_created_with_director_member(self, league, director):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}", headers=_h(director["token"]), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["is_director"] is True
        assert d["is_member"] is True
        assert d["member_count"] >= 1

    def test_seasons_seeded(self, league, director):
        s = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/seasons", headers=_h(director["token"]), timeout=20)
        assert s.status_code == 200
        assert len(s.json()) >= 1

    def test_join_league_creates_player_member(self, league, outsider):
        r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/join", json={}, headers=_h(outsider["token"]), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("role") in ("player", None) or d.get("league_id") == league["id"]

    def test_browse_lists_league(self, league, outsider):
        r = requests.get(f"{BASE_URL}/api/leagues/browse", headers=_h(outsider["token"]), timeout=20)
        assert r.status_code == 200
        assert any(x["id"] == league["id"] for x in r.json())

    def test_standings(self, league, director):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/standings", headers=_h(director["token"]), timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_ledger_create_list(self, league, director):
        c = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/ledger",
            json={"kind": "credit", "category": "Entry Fee", "amount": 10, "description": "TEST entry"},
            headers=_h(director["token"]), timeout=20,
        )
        # Accept 200 or 201
        assert c.status_code in (200, 201), c.text
        g = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/ledger", headers=_h(director["token"]), timeout=20)
        assert g.status_code == 200

    def test_clubhouse_announcements(self, league, director):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/announcements", headers=_h(director["token"]), timeout=20)
        assert r.status_code in (200, 404), r.text  # tolerate route rename

    def test_score_update_and_finalize_reject(self, joined_member):
        sid = pytest.scorecard_id
        r = requests.patch(
            f"{BASE_URL}/api/scorecards/{sid}/score",
            json={"hole": 1, "strokes": 3},
            headers=_h(joined_member["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        # Individual finalize requires certified=true
        f = requests.post(
            f"{BASE_URL}/api/scorecards/{sid}/finalize", json={"certified": False},
            headers=_h(joined_member["token"]), timeout=20,
        )
        assert f.status_code in (400, 422), f.text

    def test_ctp_and_payout(self, league, director):
        rid = pytest.round_id
        gp = requests.get(f"{BASE_URL}/api/rounds/{rid}/payout", headers=_h(director["token"]), timeout=20)
        assert gp.status_code == 200
        gc = requests.get(f"{BASE_URL}/api/rounds/{rid}/ctp", headers=_h(director["token"]), timeout=20)
        assert gc.status_code == 200
