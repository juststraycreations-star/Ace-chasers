"""Iteration 15 tests for /api/courses + /api/courses/{id}/reviews."""
from __future__ import annotations

import os
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
FIREBASE_API_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
IDENTITY = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
DELETE = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"


def _signup(prefix="i15"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        IDENTITY,
        json={"email": email, "password": "demo1234", "returnSecureToken": True},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return {"email": email, "id_token": d["idToken"], "uid": d["localId"]}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _sync(u):
    r = requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=_h(u["id_token"]), timeout=15)
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def alice():
    u = _signup("i15a")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"name": "Alice i15"},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def bob():
    u = _signup("i15b")
    _sync(u)
    requests.put(
        f"{BASE_URL}/api/users/me",
        headers=_h(u["id_token"]),
        json={"name": "Bob i15"},
        timeout=15,
    )
    yield u
    try:
        requests.post(DELETE, json={"idToken": u["id_token"]}, timeout=10)
    except Exception:
        pass


def test_courses_list_returns_seeded_courses():
    """Anonymous (public) GET /api/courses must succeed and return the
    courses seeded at boot."""
    r = requests.get(f"{BASE_URL}/api/courses", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 10, "expected at least 10 seeded courses"
    # Each course has the new aceClub fields.
    for c in data:
        assert "aceClub" in c
        assert "aceClubCount" in c
        if c["aceClub"]:
            assert c["aceClubCount"] is None or isinstance(c["aceClubCount"], int)


def test_courses_search_filters_by_name():
    r = requests.get(f"{BASE_URL}/api/courses", params={"search": "Maple"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert any("maple" in c["name"].lower() for c in data)


def test_add_review_creates_and_updates_stats(alice):
    # Pick first course
    list_resp = requests.get(f"{BASE_URL}/api/courses", timeout=15)
    courses = list_resp.json()
    course = courses[0]
    course_id = course["id"]

    r = requests.post(
        f"{BASE_URL}/api/courses/{course_id}/reviews",
        headers=_h(alice["id_token"]),
        json={"rating": 5, "body": f"Great course! {uuid.uuid4().hex[:6]}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    review = r.json()
    assert review["rating"] == 5
    assert review["is_mine"] is True
    assert review["author"]["uid"] == alice["uid"]

    # Course detail now reflects the new review.
    c = requests.get(f"{BASE_URL}/api/courses/{course_id}", timeout=15).json()
    assert c["review_count"] >= 1
    assert c["avg_rating"] is not None


def test_user_can_only_have_one_review_per_course(alice):
    """Reposting overwrites the previous review."""
    list_resp = requests.get(f"{BASE_URL}/api/courses", timeout=15)
    course_id = list_resp.json()[0]["id"]

    # First review (already exists from previous test; alice has one).
    requests.post(
        f"{BASE_URL}/api/courses/{course_id}/reviews",
        headers=_h(alice["id_token"]),
        json={"rating": 3, "body": "first try"},
        timeout=15,
    )
    # Second review for same user.
    requests.post(
        f"{BASE_URL}/api/courses/{course_id}/reviews",
        headers=_h(alice["id_token"]),
        json={"rating": 4, "body": "actually played again, better than I thought"},
        timeout=15,
    )
    # List should only have ONE review from alice for this course.
    rs = requests.get(
        f"{BASE_URL}/api/courses/{course_id}/reviews",
        headers=_h(alice["id_token"]),
        timeout=15,
    ).json()
    alice_reviews = [r for r in rs if r["author"]["uid"] == alice["uid"]]
    assert len(alice_reviews) == 1
    # And it should be the most recent one.
    assert alice_reviews[0]["body"] == "actually played again, better than I thought"
    assert alice_reviews[0]["rating"] == 4


def test_recent_reviews_endpoint_includes_course_context(alice):
    """GET /api/courses/recent-reviews returns recent reviews with
    course_name / course_location attached so the sidebar can render."""
    list_resp = requests.get(f"{BASE_URL}/api/courses", timeout=15)
    course_id = list_resp.json()[0]["id"]
    requests.post(
        f"{BASE_URL}/api/courses/{course_id}/reviews",
        headers=_h(alice["id_token"]),
        json={"rating": 5, "body": f"recent endpoint test {uuid.uuid4().hex[:6]}"},
        timeout=15,
    )
    r = requests.get(
        f"{BASE_URL}/api/courses/recent-reviews",
        headers=_h(alice["id_token"]),
        timeout=15,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    sample = rows[0]
    assert "course_name" in sample and sample["course_name"]
    assert "rating" in sample


@pytest.mark.skipif(not ADMIN_API_KEY, reason="ADMIN_API_KEY not configured")
def test_admin_can_add_a_new_course():
    """POST /api/admin/courses requires the X-Admin-Key header."""
    payload = {
        "name": f"TEST i15 Course {uuid.uuid4().hex[:6]}",
        "location": "Testville, TX",
        "holes": 18,
        "description": "Smoke-test course added by test_iteration15.",
        "aceClub": True,
        "aceClubCount": 42,
    }
    # Without the header -> 401.
    r0 = requests.post(f"{BASE_URL}/api/admin/courses", json=payload, timeout=15)
    assert r0.status_code in (401, 403)
    # With the header -> 200.
    r = requests.post(
        f"{BASE_URL}/api/admin/courses",
        headers={"X-Admin-Key": ADMIN_API_KEY},
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    course = r.json()
    assert course["aceClub"] is True
    assert course["aceClubCount"] == 42
    # Cleanup.
    requests.delete(
        f"{BASE_URL}/api/admin/courses/{course['id']}",
        headers={"X-Admin-Key": ADMIN_API_KEY},
        timeout=15,
    )
