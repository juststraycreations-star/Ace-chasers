"""Ace Chasers backend API.

All app routes are prefixed with /api and protected by `get_current_user`
(Firebase ID token via Authorization: Bearer). Routes are split across
modules in `routers/`; this file just wires the FastAPI app together.

Routers:
  auth     — /api/auth/sync, /api/users/me, /api/users/{uid}
  admin    — /api/admin/invites
  media    — /api/users/me/profile-picture, /api/users/me/banner
  discovery— /api/discovery
  social   — /api/swipes, /api/likes, /api/matches/{uid}/friend,
             /api/friend-requests/*, /api/inbox
  posts    — /api/feed, /api/posts
"""
from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

import cloud_storage  # noqa: E402
from db import (  # noqa: E402
    ensure_indexes,
    seed_demo_users,
)
from deps import require_invite_enabled  # noqa: E402
from firebase_auth import init_firebase  # noqa: E402
from posts import (  # noqa: E402
    UPLOAD_DIR,
    ensure_indexes as ensure_post_indexes,
)
from routers import (  # noqa: E402
    admin_router,
    auth_router,
    beta_router,
    courses_router,
    discovery_router,
    leagues_router,
    media_router,
    messages_router,
    news_router,
    posts_router,
    social_router,
)
from seed_courses import seed_default_courses  # noqa: E402


logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Ace Chasers API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve legacy on-disk uploads. New uploads go to Cloudinary when configured.
app.mount("/api/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.on_event("startup")
async def on_startup() -> None:
    init_firebase()
    cloud_storage.init()
    await ensure_indexes()
    await ensure_post_indexes()
    # Demo seed users (Sarah, Jessica, Amanda) and auto-likes intentionally
    # disabled — production goes live with real users only.
    # await seed_demo_users()
    # Courses are public data (real popular US courses) — seeded once if
    # collection is empty. Idempotent on every boot.
    inserted = await seed_default_courses()
    if inserted:
        logger.info("Seeded %d default courses", inserted)
    # Backfill the "First Run" founding-member flag on the earliest 100
    # real (non-seed) users so legacy accounts get the badge too. Runs
    # every boot but is idempotent — it only sets fields that are missing.
    await _backfill_first_run_flag()


async def _backfill_first_run_flag() -> None:
    """One-shot, idempotent: award first_run=true to the first 100 non-seed
    users by created_at, and default the two dismissal flags on every user
    that's missing them."""
    from db import get_db  # local import to avoid startup cycle
    db = get_db()
    # Ensure the dismissal booleans default to false for any user missing them.
    await db.users.update_many(
        {"has_dismissed_first_run_modal": {"$exists": False}},
        {"$set": {"has_dismissed_first_run_modal": False}},
    )
    await db.users.update_many(
        {"has_viewed_leagues_feature": {"$exists": False}},
        {"$set": {"has_viewed_leagues_feature": False}},
    )
    # Award first_run to the earliest 100 non-seed users. `is_seed` is set
    # true on demo bots and false for real users.
    cursor = db.users.find(
        {"$or": [{"is_seed": {"$exists": False}}, {"is_seed": False}]},
        {"_id": 0, "uid": 1, "created_at": 1, "first_run": 1},
    ).sort("created_at", 1).limit(100)
    winners = [d async for d in cursor]
    winner_uids = [d["uid"] for d in winners]
    if winner_uids:
        await db.users.update_many(
            {"uid": {"$in": winner_uids},
             "$or": [{"first_run": {"$exists": False}}, {"first_run": False}]},
            {"$set": {"first_run": True}},
        )
    # Everyone NOT in that top-100 explicitly defaults to false so the
    # ProfileOut serializer never emits null for the flag.
    await db.users.update_many(
        {"first_run": {"$exists": False}},
        {"$set": {"first_run": False}},
    )
    logger.info("First Run backfill complete: %d founding members", len(winner_uids))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    """Public config consumed by the frontend on app load."""
    return {"require_invite": require_invite_enabled()}


app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(media_router.router)
app.include_router(discovery_router.router)
app.include_router(social_router.router)
app.include_router(posts_router.router)
app.include_router(messages_router.router)
app.include_router(courses_router.router)
app.include_router(news_router.router)
app.include_router(beta_router.router)
app.include_router(leagues_router.api_router, prefix="/api")
