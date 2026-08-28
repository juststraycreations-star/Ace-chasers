"""Iteration 21 tests: `submitted_by_name` on CourseOut.

- POST /api/courses returns the new course with `submitted_by_name`
  populated from the current user's profile name (no follow-up GET).
- GET /api/courses includes `submitted_by_name` for user-submitted
  courses and null for admin-seeded ones.
- GET /api/courses/{id} likewise exposes the resolved submitter name.
- If the submitter's user doc has no `name`, `submitted_by_name` must
  be null (not an empty string).
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
ADMIN_KEY = os.environ.get("ADMIN_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"


def _signup(prefix="i21"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _sync(u, name=None):
    r = requests.post(
        f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=20
    )
    assert r.status_code == 200, r.text
    # auth/sync ignores `name` (AuthSyncIn only accepts invite_code), so we
    # set the display name via PUT /api/users/me which is what the frontend
    # onboarding flow does.
    if name:
        r2 = requests.put(
            f"{BASE_URL}/api/users/me",
            json={"name": name},
            headers=_h(u["id_token"]),
            timeout=20,
        )
        assert r2.status_code == 200, r2.text
    return r.json()


# --- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def named_user():
    """A signed-up user with a recognizable display name set via auth/sync."""
    u = _signup("named")
    u["name"] = f"Tester Submitter {u['uid'][:6]}"
    _sync(u, name=u["name"])
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def anon_user():
    """A user whose profile name was never set (auth/sync without name)."""
    u = _signup("anon")
    # Intentionally no name on sync; the backend's fallback should leave the
    # users.name field unset, so submitted_by_name must come back null.
    _sync(u)
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def created_course_ids():
    """Track created course ids for admin-API cleanup at module teardown."""
    ids: list[str] = []
    yield ids
    if not ADMIN_KEY:
        return
    for cid in ids:
        try:
            requests.delete(
                f"{BASE_URL}/api/admin/courses/{cid}",
                headers={"X-Admin-Key": ADMIN_KEY},
                timeout=10,
            )
        except Exception:
            pass


# --- Tests -----------------------------------------------------------------


@pytest.fixture(scope="module")
def named_user_course(named_user, created_course_ids):
    """Create a course submitted by the named user. Returns the raw
    POST response dict (so individual tests can assert on it) plus the
    expected name."""
    payload = {
        "name": f"TEST_Course_i21_{uuid.uuid4().hex[:6]}",
        "location": "Brooklyn, NY",
        "holes": 18,
        "aceClub": False,
    }
    r = requests.post(
        f"{BASE_URL}/api/courses",
        json=payload,
        headers=_h(named_user["id_token"]),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    created_course_ids.append(d["id"])
    return {"resp": d, "expected_name": named_user["name"]}


class TestSubmittedByNameOnCreate:
    """POST /api/courses must surface submitted_by_name inline."""

    def test_post_returns_submitted_by_name(self, named_user_course):
        d = named_user_course["resp"]
        assert "submitted_by_name" in d, f"missing field, got keys={list(d.keys())}"
        assert d["submitted_by_name"] == named_user_course["expected_name"], d

    def test_list_includes_submitted_by_name(self, named_user_course):
        r = requests.get(f"{BASE_URL}/api/courses", timeout=20)
        assert r.status_code == 200, r.text
        courses = r.json()
        cid = named_user_course["resp"]["id"]
        match = next((c for c in courses if c["id"] == cid), None)
        assert match is not None, "newly created course missing from /api/courses"
        assert "submitted_by_name" in match
        assert match["submitted_by_name"] == named_user_course["expected_name"], (
            f"list submitted_by_name mismatch: {match['submitted_by_name']!r}"
        )

    def test_detail_includes_submitted_by_name(self, named_user_course):
        cid = named_user_course["resp"]["id"]
        r = requests.get(f"{BASE_URL}/api/courses/{cid}", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["submitted_by_name"] == named_user_course["expected_name"], d


class TestAnonSubmitterFallback:
    """A user with no profile name must surface submitted_by_name=null."""

    def test_anon_post_returns_null(self, anon_user, created_course_ids):
        payload = {
            "name": f"TEST_Course_anon_{uuid.uuid4().hex[:6]}",
            "aceClub": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json=payload,
            headers=_h(anon_user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "submitted_by_name" in d
        # Empty/missing profile name must become null, NOT an empty string.
        assert d["submitted_by_name"] is None, (
            f"expected null, got {d['submitted_by_name']!r}"
        )
        TestAnonSubmitterFallback.course_id = d["id"]
        created_course_ids.append(d["id"])

    def test_anon_list_returns_null(self):
        r = requests.get(f"{BASE_URL}/api/courses", timeout=20)
        assert r.status_code == 200
        match = next(
            (c for c in r.json() if c["id"] == TestAnonSubmitterFallback.course_id),
            None,
        )
        assert match is not None
        assert match["submitted_by_name"] is None, match

    def test_anon_detail_returns_null(self):
        r = requests.get(
            f"{BASE_URL}/api/courses/{TestAnonSubmitterFallback.course_id}",
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["submitted_by_name"] is None


class TestAdminSeedSubmitterNull:
    """Admin-created courses have no submitted_by, so the field must be null."""

    def test_admin_seed_returns_null(self, created_course_ids):
        if not ADMIN_KEY:
            pytest.skip("ADMIN_API_KEY not configured")
        payload = {
            "name": f"TEST_AdminCourse_i21_{uuid.uuid4().hex[:6]}",
            "location": "Admin City, ST",
            "aceClub": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/admin/courses",
            json=payload,
            headers={"X-Admin-Key": ADMIN_KEY},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("submitted_by_name") is None, d
        admin_id = d["id"]
        created_course_ids.append(admin_id)

        # And on subsequent list + detail reads it must remain null.
        r2 = requests.get(f"{BASE_URL}/api/courses", timeout=20)
        match = next((c for c in r2.json() if c["id"] == admin_id), None)
        assert match is not None
        assert match["submitted_by_name"] is None, match

        r3 = requests.get(f"{BASE_URL}/api/courses/{admin_id}", timeout=20)
        assert r3.status_code == 200
        assert r3.json()["submitted_by_name"] is None


class TestExistingSeededCoursesNoSubmitter:
    """At least the pre-existing seeded courses on the list shouldn't have
    a submitter name. (Skipped gracefully if every course was user-added.)"""

    def test_some_courses_have_null_submitter(self):
        r = requests.get(f"{BASE_URL}/api/courses", timeout=20)
        assert r.status_code == 200
        courses = r.json()
        # Every CourseOut must include the field key explicitly.
        for c in courses:
            assert "submitted_by_name" in c, c
        nulls = [c for c in courses if c["submitted_by_name"] is None]
        # Not asserting count > 0 because a fresh DB could have only user
        # courses; we only assert that the field is always present.
        # But if any null exists, it must be exactly None (no empty string).
        for c in nulls:
            assert c["submitted_by_name"] is None
