"""Admin-only endpoints (protected by X-Admin-Key header)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import require_admin
from invites import create_invite, list_invites, revoke_invite
from models import InviteCreateIn


router = APIRouter()


@router.get("/api/admin/invites")
async def admin_list_invites(_: bool = Depends(require_admin)):
    return await list_invites()


@router.post("/api/admin/invites")
async def admin_create_invite(payload: InviteCreateIn, _: bool = Depends(require_admin)):
    return await create_invite(email=payload.email, expires_at=payload.expires_at)


@router.delete("/api/admin/invites/{code}")
async def admin_revoke_invite(code: str, _: bool = Depends(require_admin)):
    ok = await revoke_invite(code)
    if not ok:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"ok": True}
