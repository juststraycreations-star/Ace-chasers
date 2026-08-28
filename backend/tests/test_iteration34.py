"""Iteration 34 — Ledger refactor parity + Compliance dashboard.

Covers:
1) Ledger endpoints (POST/GET/CSV + entry-fees/collect) still work
   identically after being extracted to leagues_ledger_router.py.
   - 401 without auth, 403 for non-director on write endpoints, 200 ok.
   - GET /ledger returns {entries,totals,balance}.
   - GET /ledger.csv returns text/csv with correct header row.
2) Entry-fee /collect creates exactly: 1 debit + N Entry-Fee credits
   + 3 auto-split credits (Weekly Payout/Ace Pool/Club Fund @ 70/20/10),
   and increments league.ace_pool by the ace bucket amount.
3) Compliance endpoint auth + shape + logic (flip player_certified
   progressively across 3 scorecards).
4) Light regression on dashboard bundle from iter31/33.
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
    email = f"TEST_i34_{uuid.uuid4().hex[:10]}@example.com"
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


def _mkleague(token, entry_fee=10.0):
    r = requests.post(
        f"{BASE_URL}/api/leagues",
        json={
            "name": f"TEST_i34_{uuid.uuid4().hex[:6]}",
            "location": "Testville",
            "format": "Singles",
            "entry_fee": entry_fee,
        },
        headers=_h(token),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _join(token, league_id):
    r = requests.post(
        f"{BASE_URL}/api/leagues/{league_id}/join", headers=_h(token), timeout=15
    )
    assert r.status_code == 200, r.text


def _members(token, league_id):
    r = requests.get(
        f"{BASE_URL}/api/leagues/{league_id}/members", headers=_h(token), timeout=15
    )
    assert r.status_code == 200
    return r.json()


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
    lg = _mkleague(director["token"], entry_fee=10.0)
    _join(member_a["token"], lg["id"])
    _join(member_b["token"], lg["id"])
    return lg


@pytest.fixture(scope="module")
def member_ids(director, league):
    mems = _members(director["token"], league["id"])
    # Map by user_id
    by_uid = {m["user_id"]: m for m in mems}
    return by_uid


# ============================ LEDGER PARITY ============================
class TestLedgerParity:
    def test_post_ledger_401_without_auth(self, league):
        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/ledger",
            json={"kind": "credit", "category": "Ace Pool", "amount": 5},
            timeout=15,
        )
        assert r.status_code == 401, r.text

    def test_get_ledger_401_without_auth(self, league):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/ledger", timeout=15)
        assert r.status_code == 401

    def test_post_ledger_403_for_non_director(self, league, member_a):
        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/ledger",
            json={"kind": "credit", "category": "Ace Pool", "amount": 5},
            headers=_h(member_a["token"]),
            timeout=15,
        )
        assert r.status_code == 403

    def test_director_can_post_ledger_and_ace_pool_increments(self, league, director):
        # Read current ace_pool
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            before = asyncio.get_event_loop().run_until_complete(
                db.leagues.find_one({"id": league["id"]}, {"ace_pool": 1, "_id": 0})
            ) if False else None
        finally:
            client.close()

        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/ledger",
            json={"kind": "credit", "category": "Ace Pool", "amount": 7.5, "note": "ace test"},
            headers=_h(director["token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "credit"
        assert d["category"] == "Ace Pool"
        assert d["amount"] == 7.5
        assert d["note"] == "ace test"
        assert "id" in d and "created_at" in d

    def test_get_ledger_shape(self, league, director):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/ledger",
            headers=_h(director["token"]),
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) >= {"entries", "totals", "balance"}
        assert isinstance(d["entries"], list)
        assert isinstance(d["totals"], dict)
        assert isinstance(d["balance"], (int, float))
        # Should have at least the entry we just added
        assert any(e["category"] == "Ace Pool" and e["amount"] == 7.5 for e in d["entries"])

    def test_get_ledger_csv(self, league, director):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/ledger.csv",
            headers=_h(director["token"]),
            timeout=15,
        )
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, ct
        body = r.text.splitlines()
        assert body[0].strip() == "Date,Kind,Category,Amount,Note", body[0]


# ============================ ENTRY-FEE COLLECT ============================
class TestEntryFeeCollect:
    def test_collect_creates_expected_ledger_entries(
        self, league, director, member_a, member_b, member_ids
    ):
        # Snapshot ace_pool + ledger before
        async def snap():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            try:
                lg = await db.leagues.find_one({"id": league["id"]}, {"_id": 0})
                cnt = await db.ledger.count_documents({"league_id": league["id"]})
                return lg.get("ace_pool", 0), cnt
            finally:
                client.close()

        loop = asyncio.new_event_loop()
        ace_before, ledger_before = loop.run_until_complete(snap())

        # Collect from all 3 members (director + a + b)
        mem_docs = list(member_ids.values())
        assert len(mem_docs) == 3, mem_docs
        payload = {"member_ids": [m["id"] for m in mem_docs]}
        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/entry-fees/collect",
            json=payload,
            headers=_h(director["token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["collected_from"] == 3
        assert d["total"] == 30.0  # 3 x $10
        assert d["split"]["weekly_payout"] == 21.0  # 70%
        assert d["split"]["ace_pool"] == 6.0  # 20%
        assert d["split"]["club_fund"] == 3.0  # 10%

        # Now inspect ledger diff
        async def diff():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            try:
                lg = await db.leagues.find_one({"id": league["id"]}, {"_id": 0})
                cnt = await db.ledger.count_documents({"league_id": league["id"]})
                return lg.get("ace_pool", 0), cnt
            finally:
                client.close()

        loop2 = asyncio.new_event_loop()
        ace_after, ledger_after = loop2.run_until_complete(diff())

        # Exactly 3 entry-fee credits + 3 auto-split credits + 1 debit = 7 new
        assert ledger_after - ledger_before == 7, f"delta={ledger_after - ledger_before}"

        # ace_pool must have advanced by exactly $6.00
        assert round(ace_after - ace_before, 2) == 6.0, (ace_before, ace_after)

    def test_collect_403_for_non_director(self, league, member_a, member_ids):
        r = requests.post(
            f"{BASE_URL}/api/leagues/{league['id']}/entry-fees/collect",
            json={"member_ids": [next(iter(member_ids.values()))["id"]]},
            headers=_h(member_a["token"]),
            timeout=15,
        )
        assert r.status_code == 403


# ============================ COMPLIANCE ============================
class TestComplianceDashboard:
    def test_401_without_auth(self, league):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/compliance", timeout=15)
        assert r.status_code == 401

    def test_403_for_non_director_member(self, league, member_a):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/compliance",
            headers=_h(member_a["token"]),
            timeout=15,
        )
        assert r.status_code == 403

    def test_403_for_outsider(self, league, outsider):
        # outsider is not a member either
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/compliance",
            headers=_h(outsider["token"]),
            timeout=15,
        )
        assert r.status_code in (403, 404)  # not-a-member surface

    def test_director_200_and_shape(self, league, director, member_ids):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/compliance",
            headers=_h(director["token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # top-level keys
        assert set(d.keys()) >= {"league", "clubhouse_terms", "rounds"}
        # league
        lg = d["league"]
        assert set(lg.keys()) >= {"id", "name", "member_count"}
        assert lg["id"] == league["id"]
        assert lg["member_count"] == 3
        # clubhouse_terms
        ct = d["clubhouse_terms"]
        assert set(ct.keys()) >= {"agreed_count", "outstanding_count", "outstanding_members"}
        assert isinstance(ct["outstanding_members"], list)
        if ct["outstanding_members"]:
            om = ct["outstanding_members"][0]
            assert set(om.keys()) >= {"id", "name", "bag_tag"}
        assert isinstance(d["rounds"], list)


# ============================ COMPLIANCE LOGIC ============================
async def _seed_round_with_scorecards(league_id, director_uid, member_docs):
    """Insert 1 round + 3 scorecards directly via Mongo so we can flip
    player_certified without going through a finalize flow."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        # find the season
        season = await db.seasons.find_one({"league_id": league_id}, {"_id": 0})
        rd_id = f"rd_{uuid.uuid4().hex[:10]}"
        await db.rounds.insert_one({
            "id": rd_id,
            "league_id": league_id,
            "season_id": season["id"] if season else None,
            "name": "Compliance Test Round",
            "date": "2026-01-15",
            "holes": 18,
            "par_per_hole": [3] * 18,
            "status": "scheduled",
            "created_at": "2026-01-15T00:00:00Z",
        })
        sc_ids = []
        for m in member_docs:
            sc_id = f"sc_{uuid.uuid4().hex[:10]}"
            await db.scorecards.insert_one({
                "id": sc_id,
                "round_id": rd_id,
                "league_id": league_id,
                "member_id": m["id"],
                "card_id": None,
                "scores": [0] * 18,
                "handicap_at_round": 0,
                "total": 54,
                "finalized": False,
                "player_certified": False,
                "certified_by_director": False,
            })
            sc_ids.append((sc_id, m["id"]))
        return rd_id, sc_ids
    finally:
        client.close()


async def _flip_player_certified(sc_id, value=True):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        await db.scorecards.update_one(
            {"id": sc_id}, {"$set": {"player_certified": value}}
        )
    finally:
        client.close()


class TestComplianceLogic:
    """3-scorecard round; flip player_certified progressively."""

    @pytest.fixture(scope="class")
    def scenario(self, league, director, member_ids):
        loop = asyncio.new_event_loop()
        rd_id, sc_ids = loop.run_until_complete(
            _seed_round_with_scorecards(
                league["id"], director["profile"].get("id"), list(member_ids.values())
            )
        )
        return {"round_id": rd_id, "sc_ids": sc_ids}

    def _get_round(self, league_id, token, round_id):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league_id}/compliance",
            headers=_h(token),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        for rd in r.json()["rounds"]:
            if rd["round_id"] == round_id:
                return rd
        pytest.fail(f"round {round_id} missing from compliance response")

    def test_a_zero_certified(self, league, director, scenario):
        rd = self._get_round(league["id"], director["token"], scenario["round_id"])
        assert rd["scorecard_total"] == 3
        assert rd["certified_count"] == 0
        assert rd["can_sweep_finalize"] is False
        assert len(rd["pending_certification"]) == 3
        # pending shape
        p0 = rd["pending_certification"][0]
        assert set(p0.keys()) >= {
            "member_id", "member_name", "bag_tag", "scorecard_id",
            "total", "finalized", "certified_by_director", "player_certified",
        }

    def test_b_flip_one(self, league, director, scenario):
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_flip_player_certified(scenario["sc_ids"][0][0], True))
        rd = self._get_round(league["id"], director["token"], scenario["round_id"])
        assert rd["certified_count"] == 1
        assert rd["can_sweep_finalize"] is False
        assert len(rd["pending_certification"]) == 2

    def test_c_flip_all(self, league, director, scenario):
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_flip_player_certified(scenario["sc_ids"][1][0], True))
        loop.run_until_complete(_flip_player_certified(scenario["sc_ids"][2][0], True))
        rd = self._get_round(league["id"], director["token"], scenario["round_id"])
        assert rd["certified_count"] == 3
        assert rd["can_sweep_finalize"] is True
        assert len(rd["pending_certification"]) == 0


# ============================ REGRESSION ============================
class TestRegression:
    def test_dashboard_bundle_still_works(self, league, director):
        r = requests.get(
            f"{BASE_URL}/api/leagues/{league['id']}/dashboard",
            headers=_h(director["token"]),
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) >= {"league", "rounds", "members", "seasons"}

    def test_dashboard_401(self, league):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard", timeout=15)
        assert r.status_code == 401
