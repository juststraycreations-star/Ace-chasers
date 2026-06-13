"""Mongo collections, indexes, and seed data."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("db")

_client: Optional[AsyncIOMotorClient] = None


def get_db():
    """Return the Mongo database singleton."""
    global _client
    if _client is None:
        mongo_url = os.environ["MONGO_URL"]
        _client = AsyncIOMotorClient(mongo_url)
    db_name = os.environ["DB_NAME"]
    return _client[db_name]


# --- Seed data --------------------------------------------------------------

# Demo "bot" users that get inserted into the users collection on startup so
# the discovery deck has real records (with real uids). Two of them
# (seed-sarah, seed-amanda) pre-like every real user that signs up so that a
# mutual match fires the moment the real user likes them back.
SEED_PLAYERS = [
    {
        "uid": "seed-sarah",
        "email": "sarah@demo.acechasers.app",
        "name": "Sarah",
        "age": 28,
        "skillLevel": "Intermediate",
        "location": "Portland, OR",
        "favoriteCourse": "Milo McIver",
        "favoriteFrisbee": "Innova Leopard",
        "bio": "Love weekend rounds and exploring new courses!",
        "interests": ["hiking", "coffee", "tournaments"],
        "profilePictureUrl": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=400&fit=crop",
        "is_seed": True,
        "auto_like": True,
    },
    {
        "uid": "seed-jessica",
        "email": "jessica@demo.acechasers.app",
        "name": "Jessica",
        "age": 26,
        "skillLevel": "Beginner",
        "location": "Seattle, WA",
        "favoriteCourse": "Rattlesnake Ledge",
        "favoriteFrisbee": "Discraft Buzzz",
        "bio": "Just getting into disc golf, looking for friendly players!",
        "interests": ["outdoors", "casual play", "nature"],
        "profilePictureUrl": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop",
        "is_seed": True,
        "auto_like": False,
    },
    {
        "uid": "seed-amanda",
        "email": "amanda@demo.acechasers.app",
        "name": "Amanda",
        "age": 30,
        "skillLevel": "Advanced",
        "location": "Eugene, OR",
        "favoriteCourse": "Willamette Park",
        "favoriteFrisbee": "Innova Destroyer",
        "bio": "Competitive player looking for serious rounds",
        "interests": ["competitions", "fitness", "travel"],
        "profilePictureUrl": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop",
        "is_seed": True,
        "auto_like": True,
    },
]


async def ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index("uid", unique=True)
    await db.users.create_index("email")
    await db.invites.create_index("code", unique=True)
    await db.invites.create_index("email")
    await db.swipes.create_index([("from_uid", 1), ("to_uid", 1)], unique=True)
    await db.swipes.create_index("to_uid")
    await db.matches.create_index([("user_a", 1), ("user_b", 1)], unique=True)
    await db.matches.create_index("user_a")
    await db.matches.create_index("user_b")


async def seed_demo_users() -> None:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    for player in SEED_PLAYERS:
        await db.users.update_one(
            {"uid": player["uid"]},
            {
                "$setOnInsert": {**player, "created_at": now},
            },
            upsert=True,
        )
    logger.info("Seeded %d demo users", len(SEED_PLAYERS))


async def ensure_inbound_likes_for(real_uid: str) -> None:
    """For each seed player flagged auto_like=True, record a like FROM the seed
    player TO the freshly-signed-in real user. When the real user later likes
    the seed back, the swipe endpoint detects the mutual like and creates a
    Match row.
    """
    if real_uid.startswith("seed-"):
        return
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    for player in SEED_PLAYERS:
        if not player.get("auto_like"):
            continue
        await db.swipes.update_one(
            {"from_uid": player["uid"], "to_uid": real_uid},
            {
                "$setOnInsert": {
                    "from_uid": player["uid"],
                    "to_uid": real_uid,
                    "action": "like",
                    "created_at": now,
                }
            },
            upsert=True,
        )
