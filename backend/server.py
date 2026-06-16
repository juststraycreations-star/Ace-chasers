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
    discovery_router,
    media_router,
    posts_router,
    social_router,
)


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
