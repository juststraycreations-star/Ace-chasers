"""Iteration 35 — Player self-certify + Rounds-router extraction parity + Compliance user_id.

Covers:
 1) POST /api/scorecards/{id}/certify
    - 401 unauth, 404 missing, 403 non-owner, 200 owner, idempotent no dup proof_log,
      db side-effects (player_certified/at/by_uid), one ProofLog row with 'PLAYER-CERTIFIED'.
 2) Compliance endpoint reflects the self-cert: pending_certification drops, and once
    every card is certified, can_sweep_finalize flips true. Also user_id column present.
 3) leagues_rounds_router.py parity: chat POST/GET, director-notes PATCH,
    CTP POST/GET/DELETE; auth + shape checks. Also verifies routes only mount once.
"""
from __future__ import annotations
import os
import uuid
import asyncio
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
IDENTITY_SIGNUP = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
)


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _signup():
    email = f"TEST_i35_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(
        IDENTITY_SIGNUP,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=25,
    )
    assert r.status_code == 200, r.text
    tok = r.json()["idToken"]
    prof = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(tok), timeout=25)
    assert prof.status_code == 200, prof.text
    return {"email": email, "token": tok, "profile": prof.json()}


def _mkleague(token):
    r = requests.post(
        f"{BASE_URL}/api/leagues",
        json={
            "name": f"TEST_i35_{uuid.uuid4().hex[:6]}",
            "location": "Testville",
            "format": "Singles",
            "entry_fee": 5.0,
        },
        headers=_h(token),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _join(token, league_id):
    r = requests.post(f"{BASE_URL}/api/leagues/{league_id}/join", headers=_h(token), timeout=15)
    assert r.status_code == 200, r.text


def _members(token, league_id):
    r = requests.get(f"{BASE_URL}/api/leagues/{league_id}/members", headers=_h(token), timeout=15)
    assert r.status_code == 200
    return r.json()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================ FIXTURES ============================
@pytest.fixture(scope="module")
def director():
    return _signup()


@pytest.fixture(scope="module")
def member_a():
    return _signup()


@pytest.fixture(scope="module")
def member_b():
    return _signup()


@pytest.fixture(scope="module")
def outsider():
    return _signup()


@pytest.fixture(scope="module")
def league(director, member_a, member_b):
    lg = _mkleague(director["token"])
    _join(member_a["token"], lg["id"])
    _join(member_b["token"], lg["id"])
    return lg


@pytest.fixture(scope="module")
def member_ids(director, league):
    mems = _members(director["token"], league["id"])
    return {m["user_id"]: m for m in mems}


# ============================ ROUND + SCORECARDS (real API) ============================
@pytest.fixture(scope="module")
def season_id(director, league):
    r = requests.get(
        f"{BASE_URL}/api/leagues/{league['id']}/seasons",
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    seasons = r.json()
    assert seasons, "expected an auto-created season"
    return seasons[0]["id"]


@pytest.fixture(scope="module")
def round_with_cards(director, league, member_ids, season_id):
    """Director creates a round then a card containing all 3 members ->
    system inserts 3 scorecards. Returns round_id + scorecard-id-by-user_id."""
    r = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/rounds",
        json={"name": "i35 Round", "date": "2026-01-20", "holes": 18,
              "season_id": season_id},
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    round_id = r.json()["id"]
    all_member_ids = [m["id"] for m in member_ids.values()]
    r2 = requests.post(
        f"{BASE_URL}/api/rounds/{round_id}/cards",
        json={"label": "A", "player_ids": all_member_ids},
        headers=_h(director["token"]), timeout=15,
    )
    assert r2.status_code == 200, r2.text
    # Fetch scorecards via GET /rounds/{id}
    r3 = requests.get(f"{BASE_URL}/api/rounds/{round_id}", headers=_h(director["token"]), timeout=15)
    assert r3.status_code == 200
    scs = r3.json()["scorecards"]
    sc_by_member = {s["member_id"]: s["id"] for s in scs}
    return {"round_id": round_id, "sc_by_member": sc_by_member}


# ============================ SELF-CERTIFY ============================
class TestSelfCertify:
    def test_401_no_auth(self, round_with_cards, member_ids, director):
        sc_id = next(iter(round_with_cards["sc_by_member"].values()))
        r = requests.post(f"{BASE_URL}/api/scorecards/{sc_id}/certify", timeout=15)
        assert r.status_code == 401, r.text

    def test_404_unknown_scorecard(self, director):
        r = requests.post(
            f"{BASE_URL}/api/scorecards/does-not-exist/certify",
            headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 404

    def test_403_non_owner(self, round_with_cards, member_ids, member_a, member_b):
        # member_a tries to certify member_b's card
        b_member_id = member_ids[member_b["profile"]["uid"]]["id"]
        sc_id = round_with_cards["sc_by_member"][b_member_id]
        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc_id}/certify",
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r.status_code == 403, r.text
        assert "own" in r.json().get("detail", "").lower()

    def test_403_outsider(self, round_with_cards, outsider):
        sc_id = next(iter(round_with_cards["sc_by_member"].values()))
        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc_id}/certify",
            headers=_h(outsider["token"]), timeout=15,
        )
        # not-a-member surface — either 403 or 404 is acceptable
        assert r.status_code in (403, 404)

    def test_200_owner_and_db_side_effects(
        self, round_with_cards, member_ids, member_a
    ):
        a_member_id = member_ids[member_a["profile"]["uid"]]["id"]
        sc_id = round_with_cards["sc_by_member"][a_member_id]

        # snapshot proof_log count
        async def _pl_count():
            client = AsyncIOMotorClient(MONGO_URL)
            try:
                return await client[DB_NAME].proof_logs.count_documents(
                    {"scorecard_id": sc_id}
                )
            finally:
                client.close()

        before = _run(_pl_count())

        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc_id}/certify",
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["player_certified"] is True
        assert "certified_at" in d

        # DB assertions
        async def _fetch():
            client = AsyncIOMotorClient(MONGO_URL)
            try:
                sc = await client[DB_NAME].scorecards.find_one({"id": sc_id}, {"_id": 0})
                pls = await client[DB_NAME].proof_logs.find(
                    {"scorecard_id": sc_id}, {"_id": 0}
                ).to_list(100)
                return sc, pls
            finally:
                client.close()

        sc, pls = _run(_fetch())
        assert sc["player_certified"] is True
        assert sc["player_certified_at"]
        assert sc["player_certified_by_uid"] == member_a["profile"]["uid"]
        # exactly one new proof-log with PLAYER-CERTIFIED marker
        new_pls = [p for p in pls if "PLAYER-CERTIFIED" in (p.get("edited_by_name") or "")]
        assert len(new_pls) == 1, new_pls
        assert len(pls) == before + 1

    def test_idempotent_no_dup_proof_log(
        self, round_with_cards, member_ids, member_a
    ):
        a_member_id = member_ids[member_a["profile"]["uid"]]["id"]
        sc_id = round_with_cards["sc_by_member"][a_member_id]

        async def _pl_count():
            client = AsyncIOMotorClient(MONGO_URL)
            try:
                return await client[DB_NAME].proof_logs.count_documents(
                    {"scorecard_id": sc_id}
                )
            finally:
                client.close()

        before = _run(_pl_count())

        r = requests.post(
            f"{BASE_URL}/api/scorecards/{sc_id}/certify",
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d.get("already_certified") is True
        assert d["player_certified"] is True

        after = _run(_pl_count())
        assert after == before, (before, after)


# ============================ COMPLIANCE REFLECTS SELF-CERT ============================
class TestComplianceReflectsSelfCert:
    def test_after_a_certified_pending_shrinks(
        self, league, director, round_with_cards, member_a, member_ids
    ):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/compliance",
            headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        rd = next(x for x in d["rounds"] if x["round_id"] == round_with_cards["round_id"])
        # A already certified in previous test class; B + director still pending
        assert rd["scorecard_total"] == 3
        assert rd["certified_count"] == 1
        assert rd["can_sweep_finalize"] is False
        assert len(rd["pending_certification"]) == 2
        # user_id column present on every pending row
        for p in rd["pending_certification"]:
            assert "user_id" in p, p
        # outstanding_members also has user_id
        for om in d["clubhouse_terms"]["outstanding_members"]:
            assert "user_id" in om, om

    def test_all_certified_flips_sweep_true(
        self, league, director, round_with_cards, member_a, member_b, member_ids
    ):
        # certify remaining two
        for u in (director, member_b):
            mid = member_ids[u["profile"]["uid"]]["id"]
            sc_id = round_with_cards["sc_by_member"][mid]
            r = requests.post(
                f"{BASE_URL}/api/scorecards/{sc_id}/certify",
                headers=_h(u["token"]), timeout=15,
            )
            assert r.status_code == 200, r.text

        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/compliance",
            headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 200
        rd = next(x for x in r.json()["rounds"] if x["round_id"] == round_with_cards["round_id"])
        assert rd["certified_count"] == 3
        assert rd["can_sweep_finalize"] is True
        assert rd["pending_certification"] == []


# ============================ ROUNDS-ROUTER EXTRACTION PARITY ============================
@pytest.fixture(scope="module")
def side_data_round(director, league, member_ids, season_id):
    """Fresh round for chat/notes/ctp tests (don't want CTP entries to pollute cert round)."""
    r = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/rounds",
        json={"name": "i35 SideData", "date": "2026-01-22", "holes": 18,
              "par_per_hole": [3] * 18, "season_id": season_id},
        headers=_h(director["token"]), timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestChat:
    def test_get_401(self, side_data_round):
        r = requests.get(f"{BASE_URL}/api/rounds/{side_data_round['id']}/chat", timeout=15)
        assert r.status_code == 401

    def test_post_401(self, side_data_round):
        r = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/chat",
            json={"text": "hi"}, timeout=15,
        )
        assert r.status_code == 401

    def test_404_missing_round(self, director):
        r = requests.post(
            f"{BASE_URL}/api/rounds/no-such-round/chat",
            json={"text": "hi"}, headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 404

    def test_non_member_403(self, side_data_round, outsider):
        r = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/chat",
            json={"text": "hi"}, headers=_h(outsider["token"]), timeout=15,
        )
        assert r.status_code in (403, 404)

    def test_send_and_get(self, side_data_round, director, member_a):
        r = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/chat",
            json={"text": "hello i35"}, headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg["text"] == "hello i35"
        assert msg["round_id"] == side_data_round["id"]
        assert msg["user_name"]
        assert "timestamp" in msg
        # GET
        r2 = requests.get(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/chat",
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r2.status_code == 200
        arr = r2.json()
        assert isinstance(arr, list)
        assert any(m["text"] == "hello i35" for m in arr)


class TestDirectorNotes:
    def test_401(self, side_data_round):
        r = requests.patch(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/director-notes",
            json={"director_notes": "n"}, timeout=15,
        )
        assert r.status_code == 401

    def test_403_non_director(self, side_data_round, member_a):
        r = requests.patch(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/director-notes",
            json={"director_notes": "note"},
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r.status_code == 403

    def test_director_ok_and_persists(self, side_data_round, director):
        r = requests.patch(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/director-notes",
            json={"director_notes": "wear rain gear", "ctp_holes": [3, 7]},
            headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        # verify by fetching round
        g = requests.get(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}",
            headers=_h(director["token"]), timeout=15,
        )
        assert g.status_code == 200
        rd = g.json()["round"]
        assert rd["director_notes"] == "wear rain gear"
        assert rd["ctp_holes"] == [3, 7]


class TestCTP:
    def test_get_401(self, side_data_round):
        r = requests.get(f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp", timeout=15)
        assert r.status_code == 401

    def test_post_401(self, side_data_round):
        r = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp",
            json={"hole": 3, "feet": 4, "inches": 6}, timeout=15,
        )
        assert r.status_code == 401

    def test_400_invalid_hole(self, side_data_round, director):
        r = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp",
            json={"hole": 99, "feet": 4, "inches": 6},
            headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 400

    def test_400_invalid_inches(self, side_data_round, director):
        r = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp",
            json={"hole": 3, "feet": 4, "inches": 12},
            headers=_h(director["token"]), timeout=15,
        )
        assert r.status_code == 400

    def test_create_list_delete(self, side_data_round, director, member_a):
        # Create 2 entries on hole 3
        r1 = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp",
            json={"hole": 3, "feet": 5, "inches": 0},
            headers=_h(director["token"]), timeout=15,
        )
        assert r1.status_code == 200, r1.text
        e1 = r1.json()
        assert e1["hole"] == 3
        assert e1["feet"] == 5
        assert e1["inches"] == 0
        assert "id" in e1

        r2 = requests.post(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp",
            json={"hole": 3, "feet": 2, "inches": 8},
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r2.status_code == 200, r2.text
        e2 = r2.json()

        # LIST — check shape
        r3 = requests.get(
            f"{BASE_URL}/api/rounds/{side_data_round['id']}/ctp",
            headers=_h(director["token"]), timeout=15,
        )
        assert r3.status_code == 200
        d = r3.json()
        assert set(d.keys()) >= {"entries", "leaderboard", "ctp_holes"}
        assert d["ctp_holes"] == [3, 7]  # set earlier by director-notes
        assert isinstance(d["leaderboard"], dict)
        # keys may be int or str depending on JSON — Python dict has int here on server side but JSON serialises to str
        lb3 = d["leaderboard"].get("3") or d["leaderboard"].get(3)
        assert lb3 is not None
        assert len(lb3) == 2
        # best (smallest distance) is member_a's 2ft 8in = 32in vs director 5ft 0in = 60in
        assert lb3[0]["distance_inches"] == 32
        assert lb3[1]["distance_inches"] == 60

        # DELETE — non-owner non-director → 403
        r4 = requests.delete(
            f"{BASE_URL}/api/ctp/{e1['id']}",
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r4.status_code == 403
        # DELETE own by member_a → 200
        r5 = requests.delete(
            f"{BASE_URL}/api/ctp/{e2['id']}",
            headers=_h(member_a["token"]), timeout=15,
        )
        assert r5.status_code == 200
        assert r5.json() == {"ok": True}
        # DELETE remaining as director → 200
        r6 = requests.delete(
            f"{BASE_URL}/api/ctp/{e1['id']}",
            headers=_h(director["token"]), timeout=15,
        )
        assert r6.status_code == 200
        # 404 on second delete
        r7 = requests.delete(
            f"{BASE_URL}/api/ctp/{e1['id']}",
            headers=_h(director["token"]), timeout=15,
        )
        assert r7.status_code == 404


# ============================ ROUTE MOUNT SINGLE-REGISTRATION ============================
class TestRouteRegistry:
    def test_no_double_mount(self):
        """Ensure each of the moved paths is registered exactly once on the app."""
        import importlib
        server = importlib.import_module("server")
        app = server.app
        # Path templates we care about
        paths = [
            ("/api/rounds/{round_id}/chat", "POST"),
            ("/api/rounds/{round_id}/chat", "GET"),
            ("/api/rounds/{round_id}/director-notes", "PATCH"),
            ("/api/rounds/{round_id}/ctp", "POST"),
            ("/api/rounds/{round_id}/ctp", "GET"),
            ("/api/ctp/{entry_id}", "DELETE"),
            ("/api/scorecards/{scorecard_id}/certify", "POST"),
        ]
        # Enumerate app.routes
        for path, method in paths:
            hits = 0
            for r in app.routes:
                rp = getattr(r, "path", None)
                methods = getattr(r, "methods", None) or set()
                if rp == path and method in methods:
                    hits += 1
            assert hits == 1, f"{method} {path} registered {hits}x"
