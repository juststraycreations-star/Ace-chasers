"""Iteration 17 tests: GET /api/news returns aggregated disc golf news from
public RSS feeds. We mock httpx so tests never hit the network — verifying
the contract, the dedupe, and the newest-first sort."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


FAKE_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{src}</title>
    <item>
      <title>{src} story A</title>
      <link>https://example.com/{src}/a</link>
      <description>Summary A from {src}</description>
      <pubDate>Mon, 16 Jun 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>{src} story B</title>
      <link>https://example.com/{src}/b</link>
      <description>Summary B from {src}</description>
      <pubDate>Sun, 15 Jun 2026 09:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, headers=None):
        # Tag the response by URL so each "feed" returns distinct entries.
        if "ultiworld" in url:
            return _FakeResp(FAKE_FEED_XML.format(src="ultiworld"))
        if "pdga" in url:
            return _FakeResp(FAKE_FEED_XML.format(src="pdga"))
        if "reddit" in url:
            return _FakeResp(FAKE_FEED_XML.format(src="reddit"))
        return _FakeResp("<rss><channel></channel></rss>")


@pytest.fixture(autouse=True)
def reset_cache():
    # Bust the in-memory TTL cache between tests.
    from routers import news_router

    news_router._cache["fetched_at"] = 0.0
    news_router._cache["items"] = []
    yield


def test_news_endpoint_returns_aggregated_items_sorted_newest_first(monkeypatch):
    import httpx
    from fastapi.testclient import TestClient

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    # Skip the real Firebase / DB startup wiring — we only need the route.
    with patch("server.init_firebase"), patch("server.cloud_storage.init"), patch(
        "server.ensure_indexes"
    ), patch("server.ensure_post_indexes"), patch(
        "server.seed_default_courses", return_value=0
    ):
        from server import app

        with TestClient(app) as client:
            r = client.get("/api/news?limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert len(body["items"]) >= 2  # at minimum 2 unique items per source
    # Sorted newest-first: the first item's published_at is >= the second's.
    if len(body["items"]) >= 2 and body["items"][0]["published_at"] and body["items"][1]["published_at"]:
        assert body["items"][0]["published_at"] >= body["items"][1]["published_at"]
    # Each item has the required shape.
    sample = body["items"][0]
    assert all(k in sample for k in ("title", "url", "source"))


def test_news_endpoint_dedupes_by_url(monkeypatch):
    import httpx
    from fastapi.testclient import TestClient

    # All feeds return the SAME item URLs — output should dedupe.
    same_xml = FAKE_FEED_XML.format(src="duplicate")

    class _DupClient(_FakeClient):
        async def get(self, _url, headers=None):
            return _FakeResp(same_xml)

    monkeypatch.setattr(httpx, "AsyncClient", _DupClient)
    with patch("server.init_firebase"), patch("server.cloud_storage.init"), patch(
        "server.ensure_indexes"
    ), patch("server.ensure_post_indexes"), patch(
        "server.seed_default_courses", return_value=0
    ):
        from server import app

        with TestClient(app) as client:
            r = client.get("/api/news?limit=20")
    assert r.status_code == 200
    urls = [i["url"] for i in r.json()["items"]]
    assert len(urls) == len(set(urls)), "duplicate URLs should be removed"
