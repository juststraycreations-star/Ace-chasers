"""Push notification token registry (Iteration 69).

Backs the Capacitor `@capacitor/push-notifications` client on Android.
The client posts its FCM token here on every successful registration
so we can fan out real-time round updates and payout alerts.

Design notes:
  • Multi-device — the same user can have several {user_id, token}
    rows (phone + tablet). The token itself is unique globally, so we
    upsert on token.
  • No `platform` enum locked yet — we accept whatever the client
    reports ("android", "ios", "web") to keep future channel logic
    flexible.
  • The DELETE endpoint is idempotent so a re-launch after logout
    can safely clean up without needing to check existence first.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from .leagues_router import get_current_user

api_router = APIRouter()

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class PushTokenPayload(BaseModel):
    # Whatever Capacitor / the Web Push API hands us — treated as an
    # opaque string, not parsed.
    token: str
    platform: Literal["android", "ios", "web"] = "android"
    # Optional device metadata so a manager could distinguish phone vs
    # tablet if we ever surface a "your devices" list.
    device_id: Optional[str] = None
    device_name: Optional[str] = None


@api_router.post("/push/register-token")
async def register_push_token(payload: PushTokenPayload, request: Request,
                                 session_token: Optional[str] = Cookie(None),
                                 authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    if not payload.token or len(payload.token) < 8:
        raise HTTPException(status_code=400, detail="Push token missing or too short")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "token": payload.token,
        "platform": payload.platform,
        "device_id": payload.device_id,
        "device_name": payload.device_name,
        "updated_at": _now_iso(),
    }
    # Upsert on token so re-registration (a common Capacitor event on
    # cold-start) never creates a duplicate row for the same device.
    # If the same token ever migrates to a different user_id (rare —
    # only via device factory reset), we overwrite the ownership too.
    await db.push_tokens.update_one(
        {"token": payload.token},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True, "user_id": user.user_id, "platform": payload.platform}


@api_router.get("/push/tokens")
async def list_my_push_tokens(request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rows = await db.push_tokens.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("updated_at", -1).to_list(50)
    return {"tokens": rows, "count": len(rows)}


class PushTokenDeletePayload(BaseModel):
    token: str


@api_router.post("/push/unregister-token")
async def unregister_push_token(payload: PushTokenDeletePayload, request: Request,
                                  session_token: Optional[str] = Cookie(None),
                                  authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    # Scope to the caller so a bad actor can't delete another user's
    # device rows even if they know a token string.
    res = await db.push_tokens.delete_one(
        {"token": payload.token, "user_id": user.user_id}
    )
    return {"ok": True, "deleted": int(res.deleted_count)}
