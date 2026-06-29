"""Iteration 20 tests: user-facing POST /api/courses.

Validates that any signed-in user can submit a course, that duplicate
detection (name+location, case-insensitive) returns 409, that empty
name is rejected, and that auth is required. Also regression-tests the
legacy admin POST /api/admin/courses path.
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


def _signup(prefix="i20"):
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
    payload = {"name": name} if name else {}
    r = requests.post(
        f"{BASE_URL}/api/auth/sync", json=payload, headers=_h(u["id_token"]), timeout=20
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def user():
    u = _signup("user")
    _sync(u, name=f"Iter20 User {u['uid'][:6]}")
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def created_course_ids():
    """Track course ids created during the run so we can clean them up
    via the admin delete endpoint at module teardown."""
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


# --- POST /api/courses (user) ---------------------------------------------

class TestAddCourseUser:
    def test_add_course_success(self, user, created_course_ids):
        payload = {
            "name": f"TEST_Course_{uuid.uuid4().hex[:6]}",
            "location": "Austin, TX",
            "holes": 18,
            "description": "Wooded, technical layout.",
            "aceClub": True,
            "aceClubCount": 25,
        }
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json=payload,
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == payload["name"]
        assert d["location"] == payload["location"]
        assert d["holes"] == 18
        assert d["aceClub"] is True
        assert d["aceClubCount"] == 25
        assert d["review_count"] == 0
        assert d["avg_rating"] is None
        assert isinstance(d["id"], str) and len(d["id"]) > 0
        # Stash for downstream tests
        TestAddCourseUser.course_id = d["id"]
        TestAddCourseUser.course_name = payload["name"]
        TestAddCourseUser.course_location = payload["location"]
        created_course_ids.append(d["id"])

    def test_get_courses_includes_new(self, user):
        r = requests.get(f"{BASE_URL}/api/courses", timeout=20)
        assert r.status_code == 200, r.text
        ids = [c["id"] for c in r.json()]
        assert TestAddCourseUser.course_id in ids

    def test_get_single_course(self, user):
        r = requests.get(
            f"{BASE_URL}/api/courses/{TestAddCourseUser.course_id}", timeout=20
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] == TestAddCourseUser.course_id
        assert d["name"] == TestAddCourseUser.course_name

    def test_add_duplicate_returns_409(self, user):
        payload = {
            "name": TestAddCourseUser.course_name,
            "location": TestAddCourseUser.course_location,
            "aceClub": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json=payload,
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 409, r.text
        assert "already exists" in r.text.lower()

    def test_add_duplicate_case_insensitive(self, user):
        payload = {
            "name": TestAddCourseUser.course_name.upper(),
            "location": TestAddCourseUser.course_location.lower(),
            "aceClub": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json=payload,
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code == 409, r.text

    def test_empty_name_rejected(self, user):
        # Pydantic min_length=1 should reject empty string -> 422
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json={"name": "", "location": "X", "aceClub": False},
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code in (400, 422), r.text

    def test_whitespace_only_name_rejected(self, user):
        # Whitespace-only passes Pydantic but should be caught by the
        # explicit `if not name` check after .strip() -> 400.
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json={"name": "   ", "location": "X", "aceClub": False},
            headers=_h(user["id_token"]),
            timeout=20,
        )
        assert r.status_code in (400, 422), r.text

    def test_no_auth_rejected(self):
        r = requests.post(
            f"{BASE_URL}/api/courses",
            json={"name": f"TEST_NoAuth_{uuid.uuid4().hex[:6]}", "aceClub": False},
            timeout=20,
        )
        assert r.status_code in (401, 403), r.text


# --- Admin regression -------------------------------------------------------

class TestAdminAddCourseRegression:
    def test_admin_add_course_still_works(self, created_course_ids):
        if not ADMIN_KEY:
            pytest.skip("ADMIN_API_KEY not configured")
        payload = {
            "name": f"TEST_AdminCourse_{uuid.uuid4().hex[:6]}",
            "location": "Admin City, ST",
            "holes": 9,
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
        assert d["name"] == payload["name"]
        assert d["holes"] == 9
        created_course_ids.append(d["id"])

    def test_admin_add_course_requires_admin_key(self):
        payload = {
            "name": f"TEST_NoAdmin_{uuid.uuid4().hex[:6]}",
            "aceClub": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/admin/courses",
            json=payload,
            headers={"X-Admin-Key": "wrong-key"},
            timeout=20,
        )
        assert r.status_code in (401, 403), r.text
