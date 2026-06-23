"""GET /api/news — aggregated disc golf news from public RSS feeds.

Polls a small allow-list of disc golf publications, caches the result in
memory for `CACHE_TTL_SECONDS`, and returns the top N most recent items
sorted newest-first.

Sources are intentionally narrow — only well-established publications + a
high-signal subreddit. No third-party API keys required.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import httpx
from fastapi import APIRouter

from models import (
    NewsItem,
    NewsResponse,
)

logger = logging.getLogger("news")
router = APIRouter()

FEEDS: list[dict] = [
    {
        "source": "Ultiworld Disc Golf",
        "url": "https://discgolf.ultiworld.com/feed/",
    },
    {
        "source": "PDGA",
        # PDGA's /news/feed went 404; the active feed lives at /rss.xml.
        "url": "https://www.pdga.com/rss.xml",
    },
    {
        "source": "r/discgolf",
        # Reddit's RSS is gated by user-agent — feedparser handles this with
        # the agent= kwarg below.
        "url": "https://www.reddit.com/r/discgolf/top/.rss?t=week",
    },
]

CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
FETCH_TIMEOUT = 10.0
USER_AGENT = "AceChasers/1.0 (https://acechasers.net news aggregator)"

# In-memory cache shared by all workers in this process.
_cache: dict = {"fetched_at": 0.0, "items": []}
_lock = asyncio.Lock()


def _parse_dt(entry) -> Optional[str]:
    """Best-effort ISO timestamp extraction from a feedparser entry."""
    # feedparser exposes published_parsed and updated_parsed as time structs.
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _clean_summary(raw: Optional[str]) -> str:
    """Strip HTML tags + collapse whitespace so the sidebar can render the
    excerpt as plain text. Cheap-and-cheerful — feedparser already gives us
    rendered text in most cases."""
    if not raw:
        return ""
    import re

    # Remove HTML tags.
    text = re.sub(r"<[^>]+>", " ", raw)
    # Decode the most common HTML entities the sources actually emit.
    text = (
        text.replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 280:
        text = text[:277] + "…"
    return text


def _extract_thumbnail(entry) -> Optional[str]:
    """Best-effort image URL extraction from a feedparser entry. Tries every
    common RSS image location in order of reliability."""
    # 1. Yahoo Media RSS — media:thumbnail
    thumbs = entry.get("media_thumbnail") or []
    if thumbs and isinstance(thumbs, list):
        url = thumbs[0].get("url")
        if url:
            return url
    # 2. Yahoo Media RSS — media:content with type=image
    contents = entry.get("media_content") or []
    if contents and isinstance(contents, list):
        for c in contents:
            url = c.get("url")
            type_ = (c.get("type") or "").lower()
            if url and (not type_ or type_.startswith("image")):
                return url
    # 3. RSS <enclosure type="image/*">
    for enc in entry.get("enclosures") or []:
        href = enc.get("href") or enc.get("url")
        type_ = (enc.get("type") or "").lower()
        if href and type_.startswith("image"):
            return href
    # 4. First <img src="..."> inside the description / content HTML.
    import re

    candidates: list[str] = []
    summary = entry.get("summary") or ""
    if summary:
        candidates.append(summary)
    for c in entry.get("content") or []:
        if isinstance(c, dict) and c.get("value"):
            candidates.append(c["value"])
    for html in candidates:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        if m:
            return m.group(1)
    return None


async def _fetch_feed(url: str, source: str) -> list[dict]:
    """Fetch a single RSS feed and return parsed entries with metadata."""
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            xml = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("News feed fetch failed [%s] %s: %s", source, url, exc)
        return []
    parsed = feedparser.parse(xml)
    if not parsed.entries:
        logger.warning("News feed [%s] returned no entries", source)
    items: list[dict] = []
    for entry in parsed.entries[:15]:
        items.append(
            {
                "title": (entry.get("title") or "").strip(),
                "url": entry.get("link") or "",
                "summary": _clean_summary(entry.get("summary")),
                "source": source,
                "published_at": _parse_dt(entry),
                "thumbnail_url": _extract_thumbnail(entry),
            }
        )
    return items


async def _refresh_cache() -> list[dict]:
    """Refresh all feeds in parallel, merge + sort newest-first."""
    results = await asyncio.gather(
        *[_fetch_feed(f["url"], f["source"]) for f in FEEDS], return_exceptions=True
    )
    merged: list[dict] = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)
    # Sort newest-first (entries without a date go to the bottom).
    merged.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    # Dedupe by URL (some publishers re-syndicate the same article).
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in merged:
        u = item["url"]
        if not u or u in seen:
            continue
        seen.add(u)
        deduped.append(item)
    return deduped[:24]


@router.get("/api/news", response_model=NewsResponse)
async def get_news(limit: int = 10) -> NewsResponse:
    """Top trending disc golf news. Cached for 30 minutes server-side."""
    limit = max(1, min(limit, 24))
    now = time.time()
    if now - _cache["fetched_at"] > CACHE_TTL_SECONDS or not _cache["items"]:
        async with _lock:
            # Re-check inside the lock so concurrent first-callers don't
            # double-fetch.
            if now - _cache["fetched_at"] > CACHE_TTL_SECONDS or not _cache["items"]:
                _cache["items"] = await _refresh_cache()
                _cache["fetched_at"] = now
    items = _cache["items"][:limit]
    return NewsResponse(
        items=[NewsItem(**i) for i in items],
        fetched_at=datetime.fromtimestamp(_cache["fetched_at"], tz=timezone.utc).isoformat(),
        sources=[f["source"] for f in FEEDS],
    )
