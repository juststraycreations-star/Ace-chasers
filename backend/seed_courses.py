"""One-shot seed for the `courses` collection.

We populate ~15 well-known US disc golf courses on first boot if the
collection is empty. Admin can add/edit/delete via `/api/admin/courses` after
that. Ace Club + Ace Club count are conservative defaults — the user can
edit them at any time.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from db import get_db


SEED_COURSES: list[dict] = [
    {
        "name": "Maple Hill",
        "location": "Leicester, MA",
        "holes": 18,
        "description": "Home of the MVP Open. Renowned wooded course with elevation, water, and tight technical lines.",
        "aceClub": True,
        "aceClubCount": 250,
    },
    {
        "name": "Idlewild",
        "location": "Burlington, KY",
        "holes": 18,
        "description": "Top-rated wooded championship course. Long, tight, and unforgiving.",
        "aceClub": True,
        "aceClubCount": 180,
    },
    {
        "name": "Winthrop Gold",
        "location": "Rock Hill, SC",
        "holes": 18,
        "description": "Hilly, open course famous for hosting the United States Disc Golf Championship.",
        "aceClub": True,
        "aceClubCount": 320,
    },
    {
        "name": "DeLaveaga",
        "location": "Santa Cruz, CA",
        "holes": 27,
        "description": "California classic with massive elevation, ocean views, and the legendary hole 27 'Top of the World'.",
        "aceClub": True,
        "aceClubCount": 200,
    },
    {
        "name": "Northwood Black",
        "location": "Charlotte, NC",
        "holes": 18,
        "description": "Wooded championship-style course with elevation and water carries.",
        "aceClub": False,
        "aceClubCount": None,
    },
    {
        "name": "Flip City",
        "location": "Shelby, MI",
        "holes": 18,
        "description": "Long open course with grippy hyzer lines. A classic Michigan tour stop.",
        "aceClub": True,
        "aceClubCount": 90,
    },
    {
        "name": "Brewster Ridge",
        "location": "Smugglers' Notch, VT",
        "holes": 18,
        "description": "Mountain course with epic elevation drops and Vermont scenery.",
        "aceClub": False,
        "aceClubCount": None,
    },
    {
        "name": "Beaver Ranch",
        "location": "Conifer, CO",
        "holes": 27,
        "description": "Mile-high mountain course with pine-lined fairways. Crisp air, big distance.",
        "aceClub": True,
        "aceClubCount": 140,
    },
    {
        "name": "Pickard Park",
        "location": "Indianola, IA",
        "holes": 18,
        "description": "Iowa staple known for fast greens and friendly community.",
        "aceClub": False,
        "aceClubCount": None,
    },
    {
        "name": "Milo McIver East",
        "location": "Estacada, OR",
        "holes": 18,
        "description": "Pacific Northwest favorite. Lush, wooded, and home to many PDGA majors.",
        "aceClub": True,
        "aceClubCount": 160,
    },
    {
        "name": "Tyler State Park",
        "location": "Newtown, PA",
        "holes": 27,
        "description": "Pennsylvania classic with multiple loops and a strong local scene.",
        "aceClub": False,
        "aceClubCount": None,
    },
    {
        "name": "Renaissance Park",
        "location": "Charlotte, NC",
        "holes": 18,
        "description": "Urban course in the heart of Charlotte. Quick rounds, flat layout.",
        "aceClub": True,
        "aceClubCount": 75,
    },
    {
        "name": "Fountain Hills",
        "location": "Fountain Hills, AZ",
        "holes": 18,
        "description": "Desert layout with cacti, elevation, and stunning Arizona scenery.",
        "aceClub": True,
        "aceClubCount": 120,
    },
    {
        "name": "Sabattus Disc Golf",
        "location": "Sabattus, ME",
        "holes": 54,
        "description": "Three full 18-hole courses (Gold/Red/Blue) — a destination property.",
        "aceClub": True,
        "aceClubCount": 210,
    },
    {
        "name": "Hippodrome",
        "location": "Houston, TX",
        "holes": 18,
        "description": "Wooded Houston staple. Tight lines, mature trees, classic Texas heat.",
        "aceClub": False,
        "aceClubCount": None,
    },
]


async def seed_default_courses() -> int:
    """Insert SEED_COURSES into the `courses` collection only if it's empty.

    Returns the number of inserts (0 if the collection already had courses).
    Safe to call on every backend boot — no-op once seeded.
    """
    db = get_db()
    existing = await db.courses.count_documents({})
    if existing > 0:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    docs = [
        {
            "id": secrets.token_urlsafe(8),
            "name": c["name"],
            "location": c.get("location"),
            "description": c.get("description"),
            "holes": c.get("holes"),
            "aceClub": bool(c.get("aceClub", False)),
            "aceClubCount": c.get("aceClubCount"),
            "created_at": now,
        }
        for c in SEED_COURSES
    ]
    await db.courses.insert_many(docs)
    return len(docs)
