"""Invitations collection helpers.

Codes can be optionally locked to a specific email. Single-use: redeeming a
code stamps `used_by` + `used_at` and the code is rejected on subsequent
attempts. Optional `expires_at` (ISO string) is enforced at redemption time.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from db import get_db

_ALPHABET = string.ascii_uppercase + string.digits


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_code() -> str:
    """Generate a human-friendly code, e.g. ACE-7H2K-P9X4."""
    parts = ["".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(2)]
    return f"ACE-{parts[0]}-{parts[1]}"


def _normalize_email(email: Optional[str]) -> Optional[str]:
    return email.strip().lower() if email else None


async def create_invite(
    email: Optional[str] = None,
    expires_at: Optional[str] = None,
    created_by: str = "admin",
) -> dict:
    db = get_db()
    code = generate_code()
    doc = {
        "code": code,
        "email": _normalize_email(email),
        "expires_at": expires_at,
        "used_by": None,
        "used_at": None,
        "created_by": created_by,
        "created_at": _now_iso(),
    }
    await db.invites.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_invites(limit: int = 200) -> list[dict]:
    db = get_db()
    out: list[dict] = []
    async for doc in db.invites.find().sort("created_at", -1).limit(limit):
        doc.pop("_id", None)
        out.append(doc)
    return out


async def revoke_invite(code: str) -> bool:
    db = get_db()
    res = await db.invites.delete_one({"code": code})
    return res.deleted_count == 1


async def redeem_invite(code: str, uid: str, email: Optional[str]) -> dict:
    """Validate + atomically consume an invite. Raises HTTPException on
    failure. Returns the redeemed invite doc on success."""
    if not code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invite_code required",
        )

    db = get_db()
    invite = await db.invites.find_one({"code": code})
    if not invite:
        raise HTTPException(status_code=403, detail="Invalid invite code")
    if invite.get("used_by"):
        raise HTTPException(status_code=403, detail="Invite already used")

    exp = invite.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                raise HTTPException(status_code=403, detail="Invite expired")
        except ValueError:
            # Malformed expiry — treat as missing
            pass

    locked_email = invite.get("email")
    user_email = _normalize_email(email)
    if locked_email and locked_email != user_email:
        raise HTTPException(
            status_code=403,
            detail="Invite is locked to a different email address",
        )

    now = _now_iso()
    result = await db.invites.update_one(
        {"code": code, "used_by": None},
        {"$set": {"used_by": uid, "used_at": now}},
    )
    if result.modified_count != 1:
        # Lost a race — someone else just redeemed it.
        raise HTTPException(status_code=403, detail="Invite already used")

    invite["used_by"] = uid
    invite["used_at"] = now
    invite.pop("_id", None)
    return invite
