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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


# Global 500 handler — guarantees EVERY unhandled exception is returned as
# a well-formed JSON body. Previously an uncaught exception mid-response
# could leave Cloudflare with an empty payload → 520 "couldn't parse
# origin response" → the browser's service worker crashed with an
# unhandled TypeError and locked users out until a hard-refresh. This
# closes that loop from the origin side.
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled %s at %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {type(exc).__name__}",
            "path": request.url.path,
        },
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
    """Idempotent, runs on every startup. Awards first_run=true to the
    earliest FOUNDING_LIMIT real (non-seed, non-test-email) users by
    created_at. Resets any legacy first_run=true rows that fail the real-
    user filter so the badge count in production stays accurate as we
    grow past the founding tier.

    A real user is:
      - not `is_seed: true`, AND
      - email is null OR does not match a testing-agent pattern
        (@example.com, prefix `test`, `qa_`, `demo_`, `bgtest`, `btnclk`,
        `testi`, `testjoiner`).
    """
    from db import get_db  # local import to avoid startup cycle
    db = get_db()

    FOUNDING_LIMIT = 40  # per user request Feb 2026

    # Regex for known test-agent email patterns (case-insensitive).
    test_email_re = r"(^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner))|(@example\.com$)"

    real_user_filter = {
        "$and": [
            {"$or": [{"is_seed": {"$exists": False}}, {"is_seed": False}]},
            {"$or": [
                {"email": None},
                {"email": ""},
                {"email": {"$exists": False}},
                {"email": {"$not": {"$regex": test_email_re, "$options": "i"}}},
            ]},
        ]
    }

    # Ensure the dismissal booleans default to false for any user missing them.
    await db.users.update_many(
        {"has_dismissed_first_run_modal": {"$exists": False}},
        {"$set": {"has_dismissed_first_run_modal": False}},
    )
    await db.users.update_many(
        {"has_viewed_leagues_feature": {"$exists": False}},
        {"$set": {"has_viewed_leagues_feature": False}},
    )

    # Pick the earliest FOUNDING_LIMIT real users by created_at. Their uids
    # are the winners.
    cursor = db.users.find(
        real_user_filter,
        {"_id": 0, "uid": 1, "created_at": 1},
    ).sort("created_at", 1).limit(FOUNDING_LIMIT)
    winners = [d async for d in cursor]
    winner_uids = [d["uid"] for d in winners]

    # Award true to winners, reset false on everyone else (so misfires from
    # earlier boots or test data don't linger).
    if winner_uids:
        await db.users.update_many(
            {"uid": {"$in": winner_uids}},
            {"$set": {"first_run": True}},
        )
    await db.users.update_many(
        {"uid": {"$nin": winner_uids}},
        {"$set": {"first_run": False}},
    )

    total_real = await db.users.count_documents(real_user_filter)
    logger.info(
        "First Run backfill complete: %d founding members (of %d real users, limit=%d)",
        len(winner_uids), total_real, FOUNDING_LIMIT,
    )


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
