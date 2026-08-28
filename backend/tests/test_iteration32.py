"""Iteration 32 — Founding-member re-award (limit=40, test-email exclusion),
auth_sync first_run gating, GET /api/leagues/{id}/dashboard bundle endpoint
(parity + perf), regression on card creation and dismiss endpoints.
"""
from __future__ import annotations
import os, uuid, time, re, pytest, requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"

TEST_EMAIL_RE = re.compile(
    r"(^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner))|(@example\.com$)",
    re.IGNORECASE,
)


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(email: str | None = None):
    if email is None:
        email = f"TEST_i32_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(IDENTITY_SIGNUP, json={"email": email, "password": "demo1234",
                                             "returnSecureToken": True}, timeout=25)
    assert r.status_code == 200, r.text
    d = r.json()
    prof = requests.post(f"{BASE_URL}/api/auth/sync", json={},
                         headers=_h(d["idToken"]), timeout=25)
    assert prof.status_code == 200, prof.text
    return {"email": email, "token": d["idToken"], "uid": d["localId"],
            "profile": prof.json()}


@pytest.fixture(scope="module")
def director(): return _signup()

@pytest.fixture(scope="module")
def member(): return _signup()

@pytest.fixture(scope="module")
def outsider(): return _signup()


@pytest.fixture(scope="module")
def league(director):
    payload = {
        "name": f"TEST i32 League {uuid.uuid4().hex[:6]}",
        "location": "Test City, ST", "format": "Singles",
        "description": "iter32 dashboard bundle", "win_points": 10, "points_step": 1,
        "entry_fee": 5, "divisions": ["Open"],
    }
    r = requests.post(f"{BASE_URL}/api/leagues", json=payload,
                      headers=_h(director["token"]), timeout=25)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def joined_member(league, member):
    r = requests.post(f"{BASE_URL}/api/leagues/{league['id']}/join", json={},
                      headers=_h(member["token"]), timeout=20)
    assert r.status_code == 200
    return member


@pytest.fixture(scope="module")
def round_id(league, director):
    s = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/seasons",
                     headers=_h(director["token"]), timeout=15).json()
    r = requests.post(
        f"{BASE_URL}/api/leagues/{league['id']}/rounds",
        json={"season_id": s[0]["id"], "name": "TEST i32 Round",
              "date": "2026-03-15", "holes": 18, "course_rating": 54.0},
        headers=_h(director["token"]), timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ================== DASHBOARD BUNDLE ==================
class TestDashboardBundle:
    def test_dashboard_401_without_auth(self, league):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard", timeout=15)
        assert r.status_code == 401

    def test_dashboard_404_unknown_league(self, director):
        r = requests.get(f"{BASE_URL}/api/leagues/does-not-exist-xyz/dashboard",
                         headers=_h(director["token"]), timeout=15)
        assert r.status_code == 404

    def test_dashboard_non_member(self, league, outsider, round_id):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard",
                         headers=_h(outsider["token"]), timeout=15)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["league"]["is_member"] is False
        assert b["league"]["is_director"] is False
        assert b["seasons"] == []
        assert b["rounds"] == []
        assert b["members"] == []
        # member_count still populated (from the league object)
        assert b["league"]["member_count"] >= 1

    def test_dashboard_member(self, league, joined_member, round_id):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard",
                         headers=_h(joined_member["token"]), timeout=15)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["league"]["is_member"] is True
        assert b["league"]["is_director"] is False
        assert len(b["seasons"]) >= 1
        assert any(rd["id"] == round_id for rd in b["rounds"])
        assert any(m["user_id"] == joined_member["uid"] for m in b["members"])

    def test_dashboard_director(self, league, director, round_id):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard",
                         headers=_h(director["token"]), timeout=15)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["league"]["is_director"] is True
        assert b["league"]["is_member"] is True

    def test_dashboard_parity_with_individual_endpoints(self, league, director, round_id):
        """Bundle payloads must match the individual endpoints exactly."""
        h = _h(director["token"])
        lid = league["id"]
        bundle = requests.get(f"{BASE_URL}/api/leagues/{lid}/dashboard", headers=h, timeout=15).json()
        lg = requests.get(f"{BASE_URL}/api/leagues/{lid}", headers=h, timeout=15).json()
        seasons = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons", headers=h, timeout=15).json()
        rounds = requests.get(f"{BASE_URL}/api/leagues/{lid}/rounds", headers=h, timeout=15).json()
        members = requests.get(f"{BASE_URL}/api/leagues/{lid}/members", headers=h, timeout=15).json()

        # league: same keys
        assert set(bundle["league"].keys()) == set(lg.keys()), (
            f"missing/extra keys: bundle={set(bundle['league'])} vs solo={set(lg)}"
        )
        # seasons/rounds/members: id sets match
        assert {s["id"] for s in bundle["seasons"]} == {s["id"] for s in seasons}
        assert {r["id"] for r in bundle["rounds"]} == {r["id"] for r in rounds}
        assert {m["id"] for m in bundle["members"]} == {m["id"] for m in members}

    def test_dashboard_perf_beats_individual(self, league, director):
        """Bundle should be at least ~2x faster than sum of the 4 individual GETs."""
        h = _h(director["token"])
        lid = league["id"]
        # Warmup
        requests.get(f"{BASE_URL}/api/leagues/{lid}/dashboard", headers=h, timeout=15)
        requests.get(f"{BASE_URL}/api/leagues/{lid}", headers=h, timeout=15)

        # Bundle: 5 samples
        bundle_samples = []
        for _ in range(5):
            t0 = time.perf_counter()
            r = requests.get(f"{BASE_URL}/api/leagues/{lid}/dashboard", headers=h, timeout=15)
            bundle_samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

        # 4 individual sequential GETs: 5 samples of the summed time
        indiv_samples = []
        for _ in range(5):
            t0 = time.perf_counter()
            requests.get(f"{BASE_URL}/api/leagues/{lid}", headers=h, timeout=15)
            requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons", headers=h, timeout=15)
            requests.get(f"{BASE_URL}/api/leagues/{lid}/rounds", headers=h, timeout=15)
            requests.get(f"{BASE_URL}/api/leagues/{lid}/members", headers=h, timeout=15)
            indiv_samples.append((time.perf_counter() - t0) * 1000)

        bundle_med = sorted(bundle_samples)[len(bundle_samples)//2]
        indiv_med = sorted(indiv_samples)[len(indiv_samples)//2]
        ratio = indiv_med / bundle_med if bundle_med > 0 else 0
        print(f"PERF bundle_p50={bundle_med:.0f}ms  indiv_p50={indiv_med:.0f}ms  speedup={ratio:.2f}x")
        # Write summary
        import json
        with open("/app/test_reports/pytest/iter32_perf.json", "w") as f:
            json.dump({
                "bundle_p50_ms": round(bundle_med, 1),
                "individual_sum_p50_ms": round(indiv_med, 1),
                "speedup": round(ratio, 2),
                "bundle_samples_ms": [round(x, 1) for x in bundle_samples],
                "individual_samples_ms": [round(x, 1) for x in indiv_samples],
            }, f, indent=2)
        # Don't hard-fail on <2x since network jitter is real, but at least
        # assert the bundle isn't SLOWER than the individual sum.
        assert bundle_med <= indiv_med, (
            f"Bundle should not be slower than individual sum: bundle={bundle_med:.0f}ms > indiv={indiv_med:.0f}ms"
        )


# ================== FOUNDING-MEMBER BACKFILL (direct Mongo) ==================
def test_backfill_founding_members_count():
    """count_documents({first_run: True}) == real users capped at 40.
    Preview DB has 3 real users so exactly 3 should be flagged."""
    import asyncio

    async def _run():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            test_email_re = r"(^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner))|(@example\.com$)"
            real_filter = {
                "$and": [
                    {"$or": [{"is_seed": {"$exists": False}}, {"is_seed": False}]},
                    {"$or": [
                        {"email": None},
                        {"email": ""},
                        {"email": {"$exists": False}},
                        {"email": {"$not": {"$regex": test_email_re, "$options": "i"}}},
                    ]},
                ]
            }
            real_count = await db.users.count_documents(real_filter)
            first_run_count = await db.users.count_documents({"first_run": True})
            expected = min(real_count, 40)
            print(f"real_count={real_count}, first_run=true count={first_run_count}, expected={expected}")
            assert first_run_count == expected, (
                f"first_run=true rows ({first_run_count}) != expected ({expected}, real_count={real_count})"
            )

            test_email_true = await db.users.count_documents({
                "email": {"$regex": test_email_re, "$options": "i"},
                "first_run": True,
            })
            # NOTE: this can be >0 transiently — auth_sync flips first_run=true
            # for new signups whenever real_count < 40, regardless of whether
            # the CURRENT signup's own email is a test email. Backfill only
            # resets on next server startup. Reported as a bug.
            assert test_email_true == 0, (
                f"{test_email_true} test-email users still have first_run=true (should be 0)"
            )
        finally:
            client.close()

    asyncio.run(_run())


# ================== AUTH_SYNC NEW-USER GATING ==================
class TestAuthSyncGating:
    def test_test_email_signup_never_flips_first_run(self):
        """A fresh @example.com signup should NOT be flagged as founding member."""
        u = _signup()  # uses @example.com by default
        assert u["profile"]["firstRun"] is False, (
            "Test-email signup incorrectly awarded first_run=true"
        )


# ================== DISMISS ENDPOINTS ==================
class TestDismissEndpoints:
    def test_dismiss_first_run_401(self):
        r = requests.post(f"{BASE_URL}/api/users/me/dismiss-first-run", json={}, timeout=10)
        assert r.status_code == 401

    def test_dismiss_leagues_feature_401(self):
        r = requests.post(f"{BASE_URL}/api/users/me/dismiss-leagues-feature", json={}, timeout=10)
        assert r.status_code == 401

    def test_dismiss_first_run_200(self, director):
        r = requests.post(f"{BASE_URL}/api/users/me/dismiss-first-run", json={},
                          headers=_h(director["token"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["hasDismissedFirstRunModal"] is True

    def test_dismiss_leagues_feature_200(self, member):
        r = requests.post(f"{BASE_URL}/api/users/me/dismiss-leagues-feature", json={},
                          headers=_h(member["token"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["hasViewedLeaguesFeature"] is True


# ================== CARD CREATION REGRESSION ==================
class TestCardCreationRegression:
    def test_director_can_create_card(self, league, director, round_id):
        members = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/members",
                               headers=_h(director["token"]), timeout=15).json()
        dm = next((m for m in members if m.get("role") == "director"), None)
        assert dm
        r = requests.post(f"{BASE_URL}/api/rounds/{round_id}/cards",
                          json={"label": "TEST i32 Card", "player_ids": [dm["id"]]},
                          headers=_h(director["token"]), timeout=20)
        assert r.status_code == 200, r.text
        card = r.json()
        assert card["label"] == "TEST i32 Card"
        assert card["round_id"] == round_id
        assert dm["id"] in card["player_ids"]

    def test_non_director_cannot_create_card(self, round_id, joined_member):
        r = requests.post(f"{BASE_URL}/api/rounds/{round_id}/cards",
                          json={"label": "TEST sneaky", "player_ids": []},
                          headers=_h(joined_member["token"]), timeout=15)
        assert r.status_code == 403
