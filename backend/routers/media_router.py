"""Image-upload endpoints for profile picture and banner.

Magic-byte sniffing happens before any disk/cloud write. When Cloudinary is
configured (CLOUDINARY_* env vars set), we upload there; otherwise we fall
back to `UPLOAD_DIR` and serve via the StaticFiles mount on /api/uploads.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import cloud_storage
from db import get_db
from deps import claims_email_verified, user_to_profile
from firebase_auth import get_current_user
from models import ProfileOut
from posts import MAX_IMAGE_BYTES, MIME_TO_EXT, UPLOAD_DIR, sniff_image_mime


router = APIRouter()


async def _save_image_for_user(image: UploadFile, uid: str, prefix: str) -> str:
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")
    real_mime = sniff_image_mime(data)
    if real_mime is None:
        raise HTTPException(
            status_code=400,
            detail="File is not a supported image (jpeg/png/webp/gif)",
        )
    ext = MIME_TO_EXT[real_mime]
    safe_uid = uid.replace("/", "_")
    base = f"{prefix}-{safe_uid}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}"

    if cloud_storage.is_enabled():
        res = cloud_storage.upload_bytes(
            data,
            folder=f"acechasers/{prefix}",
            public_id=base,
            resource_type="image",
        )
        return res["secure_url"]

    filename = f"{base}.{ext}"
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(data)
    return f"/api/uploads/{filename}"


@router.post("/api/users/me/profile-picture", response_model=ProfileOut)
async def upload_profile_picture(
    image: UploadFile = File(...),
    current=Depends(get_current_user),
):
    url = await _save_image_for_user(image, current["uid"], prefix="pic")
    db = get_db()
    await db.users.update_one(
        {"uid": current["uid"]},
        {"$set": {"profilePictureUrl": url, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    doc = await db.users.find_one({"uid": current["uid"]})
    return user_to_profile(doc, email_verified=claims_email_verified(current.get("claims") or {}))


@router.post("/api/users/me/banner", response_model=ProfileOut)
async def upload_banner(
    image: UploadFile = File(...),
    current=Depends(get_current_user),
):
    url = await _save_image_for_user(image, current["uid"], prefix="banner")
    db = get_db()
    await db.users.update_one(
        {"uid": current["uid"]},
        {"$set": {"bannerUrl": url, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    doc = await db.users.find_one({"uid": current["uid"]})
    return user_to_profile(doc, email_verified=claims_email_verified(current.get("claims") or {}))
