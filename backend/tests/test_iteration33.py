"""Iteration 33 — Retest iter32 blockers on auth_sync first_run gating.

Focus:
1) Fresh @example.com signup must NOT get first_run=true.
2) Mongo count_documents({first_run: True}) must equal real-user count
   (capped at 40) both BEFORE and AFTER a fresh test-email signup — no drift.
3) Positive path: a non test-email signup while real_count<40 must get
   first_run=true.
4) Regression on dashboard bundle, card creation, dismiss endpoints.
"""
from __future__ import annotations
import os, uuid, time, re, pytest, requests, asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
IDENTITY_SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"

TEST_EMAIL_RE_STR = r"(^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner))|(@example\.com$)"

REAL_USER_FILTER = {
    "$and": [
        {"$or": [{"is_seed": {"$exists": False}}, {"is_seed": False}]},
        {"$or": [
            {"email": None},
            {"email": ""},
            {"email": {"$exists": False}},
            {"email": {"$not": {"$regex": TEST_EMAIL_RE_STR, "$options": "i"}}},
        ]},
    ]
}


def _h(t): return {"Authorization": f"Bearer {t}"}


def _signup(email: str | None = None):
    if email is None:
        email = f"TEST_i33_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(IDENTITY_SIGNUP, json={"email": email, "password": "demo1234",
                                             "returnSecureToken": True}, timeout=25)
    assert r.status_code == 200, r.text
    d = r.json()
    prof = requests.post(f"{BASE_URL}/api/auth/sync", json={},
                         headers=_h(d["idToken"]), timeout=25)
    assert prof.status_code == 200, prof.text
    return {"email": email, "token": d["idToken"], "uid": d["localId"],
            "profile": prof.json()}


async def _mongo_counts():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        real_count = await db.users.count_documents(REAL_USER_FILTER)
        first_run_count = await db.users.count_documents({"first_run": True})
        test_email_first_run = await db.users.count_documents({
            "email": {"$regex": TEST_EMAIL_RE_STR, "$options": "i"},
            "first_run": True,
        })
        return real_count, first_run_count, test_email_first_run
    finally:
        client.close()


# ============================ CORE BLOCKER RETESTS ============================
class TestAuthSyncFirstRunGating:

    def test_test_email_signup_never_flips_first_run(self):
        """(a) A fresh TEST_i33_xxx@example.com signup must NOT get firstRun=true."""
        u = _signup()  # defaults to @example.com
        fr = u["profile"].get("firstRun")
        print(f"signup email={u['email']} -> firstRun={fr}")
        assert fr is False, f"Test-email signup incorrectly awarded first_run=true: {u['profile']}"

    def test_first_run_count_no_drift_after_test_email_signup(self):
        """(b) count_documents({first_run: True}) must equal min(real_count, 40)
        BOTH before and after a test-email signup — no drift ever."""
        real_before, fr_before, test_fr_before = asyncio.run(_mongo_counts())
        expected_before = min(real_before, 40)
        print(f"BEFORE: real={real_before}, first_run=true={fr_before}, "
              f"test_email_first_run={test_fr_before}, expected={expected_before}")
        assert fr_before == expected_before, (
            f"[BEFORE] first_run drift: {fr_before} != {expected_before} "
            f"(real_count={real_before})"
        )
        assert test_fr_before == 0, (
            f"[BEFORE] {test_fr_before} test-email users still have first_run=true"
        )

        # New test-email signup — must NOT affect any of the counts
        u = _signup()
        assert u["profile"].get("firstRun") is False, "profile.firstRun leaked true"

        real_after, fr_after, test_fr_after = asyncio.run(_mongo_counts())
        expected_after = min(real_after, 40)
        print(f"AFTER:  real={real_after}, first_run=true={fr_after}, "
              f"test_email_first_run={test_fr_after}, expected={expected_after}")

        # Real-user count must not have changed (test-email signup)
        assert real_after == real_before, (
            f"Real-user count moved on a test-email signup: {real_before} -> {real_after}"
        )
        assert fr_after == expected_after, (
            f"[AFTER] first_run drift: {fr_after} != {expected_after}"
        )
        assert fr_after == fr_before, (
            f"first_run count changed after test-email signup: {fr_before} -> {fr_after}"
        )
        assert test_fr_after == 0, (
            f"[AFTER] {test_fr_after} test-email users incorrectly hold first_run=true"
        )

    def test_non_test_email_signup_gets_first_run_true(self):
        """Positive path: yourfriend+manual@somedomain.com while real_count<40
        must get firstRun=true."""
        real_before, fr_before, _ = asyncio.run(_mongo_counts())
        assert real_before < 40, f"Preview DB already at founding cap (real={real_before})"

        # Non test-email domain, unique prefix to avoid test_email_re match.
        email = f"friend_manual_{uuid.uuid4().hex[:8]}@somedomain.com"
        # Sanity: our own regex should NOT match this
        assert not re.search(TEST_EMAIL_RE_STR, email, re.IGNORECASE), \
            f"chosen email would match test_email_re: {email}"

        u = _signup(email=email)
        fr = u["profile"].get("firstRun")
        print(f"non-test signup {email} -> firstRun={fr}")
        assert fr is True, f"Non test-email signup did NOT get first_run=true: {u['profile']}"

        real_after, fr_after, test_fr_after = asyncio.run(_mongo_counts())
        print(f"AFTER real={real_after} fr={fr_after} test_fr={test_fr_after}")
        # Real count should tick up by exactly 1
        assert real_after == real_before + 1, (
            f"Real-user count expected {real_before + 1}, got {real_after}"
        )
        # first_run count should also tick up by 1 (still under 40)
        assert fr_after == fr_before + 1, (
            f"first_run count expected {fr_before + 1}, got {fr_after}"
        )
        # No drift: first_run count must still equal min(real, 40)
        assert fr_after == min(real_after, 40), (
            f"drift: fr_after={fr_after} vs min(real,40)={min(real_after, 40)}"
        )
        # No test-email account should hold first_run=true
        assert test_fr_after == 0, (
            f"{test_fr_after} test-email users incorrectly hold first_run=true"
        )


# =============================== REGRESSION ==================================
# Reuse module fixtures for dashboard/card/dismiss regression.

@pytest.fixture(scope="module")
def director(): return _signup()

@pytest.fixture(scope="module")
def member(): return _signup()

@pytest.fixture(scope="module")
def outsider(): return _signup()


@pytest.fixture(scope="module")
def league(director):
    payload = {
        "name": f"TEST i33 League {uuid.uuid4().hex[:6]}",
        "location": "Test City, ST", "format": "Singles",
        "description": "iter33 regression", "win_points": 10, "points_step": 1,
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
        json={"season_id": s[0]["id"], "name": "TEST i33 Round",
              "date": "2026-03-15", "holes": 18, "course_rating": 54.0},
        headers=_h(director["token"]), timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestDashboardBundleRegression:
    def test_dashboard_401_no_auth(self, league):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard", timeout=15)
        assert r.status_code == 401

    def test_dashboard_director_200(self, league, director, round_id):
        r = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/dashboard",
                         headers=_h(director["token"]), timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b["league"]["is_director"] is True
        assert len(b["seasons"]) >= 1
        assert any(rd["id"] == round_id for rd in b["rounds"])

    def test_dashboard_parity_with_individual(self, league, director, round_id):
        h = _h(director["token"])
        lid = league["id"]
        bundle = requests.get(f"{BASE_URL}/api/leagues/{lid}/dashboard", headers=h, timeout=15).json()
        lg = requests.get(f"{BASE_URL}/api/leagues/{lid}", headers=h, timeout=15).json()
        seasons = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons", headers=h, timeout=15).json()
        rounds = requests.get(f"{BASE_URL}/api/leagues/{lid}/rounds", headers=h, timeout=15).json()
        members = requests.get(f"{BASE_URL}/api/leagues/{lid}/members", headers=h, timeout=15).json()
        assert set(bundle["league"].keys()) == set(lg.keys())
        assert {s["id"] for s in bundle["seasons"]} == {s["id"] for s in seasons}
        assert {r["id"] for r in bundle["rounds"]} == {r["id"] for r in rounds}
        assert {m["id"] for m in bundle["members"]} == {m["id"] for m in members}

    def test_dashboard_perf_not_slower(self, league, director):
        h = _h(director["token"])
        lid = league["id"]
        # warmup
        requests.get(f"{BASE_URL}/api/leagues/{lid}/dashboard", headers=h, timeout=15)
        bundle_samples, indiv_samples = [], []
        for _ in range(4):
            t0 = time.perf_counter()
            requests.get(f"{BASE_URL}/api/leagues/{lid}/dashboard", headers=h, timeout=15)
            bundle_samples.append((time.perf_counter() - t0) * 1000)
        for _ in range(4):
            t0 = time.perf_counter()
            requests.get(f"{BASE_URL}/api/leagues/{lid}", headers=h, timeout=15)
            requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons", headers=h, timeout=15)
            requests.get(f"{BASE_URL}/api/leagues/{lid}/rounds", headers=h, timeout=15)
            requests.get(f"{BASE_URL}/api/leagues/{lid}/members", headers=h, timeout=15)
            indiv_samples.append((time.perf_counter() - t0) * 1000)
        bp = sorted(bundle_samples)[len(bundle_samples)//2]
        ip = sorted(indiv_samples)[len(indiv_samples)//2]
        print(f"PERF bundle_p50={bp:.0f}ms indiv_p50={ip:.0f}ms speedup={ip/bp:.2f}x")
        assert bp <= ip, f"bundle slower than individual sum: {bp:.0f} > {ip:.0f}"


class TestCardCreationRegression:
    def test_director_can_create_card(self, league, director, round_id):
        members = requests.get(f"{BASE_URL}/api/leagues/{league['id']}/members",
                               headers=_h(director["token"]), timeout=15).json()
        dm = next((m for m in members if m.get("role") == "director"), None)
        assert dm
        r = requests.post(f"{BASE_URL}/api/rounds/{round_id}/cards",
                          json={"label": "TEST i33 Card", "player_ids": [dm["id"]]},
                          headers=_h(director["token"]), timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["label"] == "TEST i33 Card"

    def test_non_director_cannot_create_card(self, round_id, joined_member):
        r = requests.post(f"{BASE_URL}/api/rounds/{round_id}/cards",
                          json={"label": "TEST sneaky", "player_ids": []},
                          headers=_h(joined_member["token"]), timeout=15)
        assert r.status_code == 403


class TestDismissEndpointsRegression:
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
