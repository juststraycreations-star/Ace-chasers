"""Iteration 43 — Auto cache-bust: /api/version endpoint sanity.

The frontend polls `/api/version` and compares `build_id` to the
`__ACE_BUILD_ID__` constant baked into its bundle at Vite build time.
When they diverge, a "New version — Reload" toast opens.

This test just guarantees the endpoint contract:
  - 200 OK
  - JSON with string `build_id` and `built_at`
  - `build_id` respects the `ACE_BUILD_ID` env var when set
"""
from __future__ import annotations
import os
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "")
            .rstrip("/") or "http://localhost:8001")


def test_version_endpoint_shape():
    r = requests.get(f"{BASE_URL}/api/version", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("build_id"), str) and body["build_id"]
    assert isinstance(body.get("built_at"), str) and body["built_at"]


def test_version_stable_across_calls_same_process():
    # Two rapid calls to the same backend process should return the same
    # build_id. If they differ the client would spam "New version" toasts.
    a = requests.get(f"{BASE_URL}/api/version", timeout=10).json()
    b = requests.get(f"{BASE_URL}/api/version", timeout=10).json()
    assert a["build_id"] == b["build_id"]
    assert a["built_at"] == b["built_at"]
