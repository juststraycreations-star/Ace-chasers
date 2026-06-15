"""Thin wrapper around the Cloudinary SDK for backend-direct uploads.

We chose backend-direct (not signed frontend uploads) because:
  * The backend already enforces Firebase Authorization on every endpoint.
  * The backend does magic-byte MIME sniffing for security — we want that to
    run *before* the file ever reaches Cloudinary.
  * It keeps the upload contract the frontend already speaks (multipart) so
    the React side doesn't need to change.

If CLOUDINARY_* env vars are missing, `is_enabled()` returns False and callers
should fall back to the on-disk uploads/ flow.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import cloudinary
import cloudinary.uploader

logger = logging.getLogger("cloud_storage")

_CONFIGURED = False


def is_enabled() -> bool:
    """True when all three Cloudinary env vars are populated."""
    return bool(
        os.environ.get("CLOUDINARY_CLOUD_NAME")
        and os.environ.get("CLOUDINARY_API_KEY")
        and os.environ.get("CLOUDINARY_API_SECRET")
    )


def init() -> bool:
    """Initialize the Cloudinary SDK once; idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return True
    if not is_enabled():
        logger.warning("Cloudinary env vars missing — uploads will fall back to local disk")
        return False
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    _CONFIGURED = True
    logger.info("Cloudinary initialized for cloud %s", os.environ["CLOUDINARY_CLOUD_NAME"])
    return True


def upload_bytes(
    data: bytes,
    *,
    folder: str,
    public_id: str,
    resource_type: str = "image",
) -> dict:
    """Upload raw bytes to Cloudinary. Returns the API response dict; callers
    care about `secure_url` and `public_id`.

    `resource_type` must be 'image' or 'video' (auto-detection is intentionally
    avoided so we never let Cloudinary infer something different than the
    magic-byte sniff did).
    """
    init()
    if not _CONFIGURED:
        raise RuntimeError("Cloudinary not configured")
    res = cloudinary.uploader.upload(
        data,
        folder=folder,
        public_id=public_id,
        resource_type=resource_type,
        overwrite=True,
        use_filename=False,
        unique_filename=False,
    )
    return res


def destroy(public_id: str, *, resource_type: str = "image") -> bool:
    """Delete an asset. Returns True when Cloudinary reports `ok` or `not found`
    (idempotent from the caller's perspective)."""
    init()
    if not _CONFIGURED:
        return False
    try:
        res = cloudinary.uploader.destroy(
            public_id, invalidate=True, resource_type=resource_type
        )
        return res.get("result") in {"ok", "not found"}
    except Exception as exc:  # pragma: no cover
        logger.warning("Cloudinary destroy failed for %s: %s", public_id, exc)
        return False


def public_id_from_url(url: Optional[str]) -> Optional[str]:
    """Extract the `folder/filename` (without extension) from a Cloudinary
    secure_url. Returns None for non-Cloudinary URLs."""
    if not url or "res.cloudinary.com" not in url:
        return None
    # Format: https://res.cloudinary.com/<cloud>/<resource_type>/upload/[v123/]<folder>/<file>.<ext>
    try:
        after_upload = url.split("/upload/", 1)[1]
    except IndexError:
        return None
    # Drop optional version prefix like v1234567890/
    parts = after_upload.split("/", 1)
    if len(parts) == 2 and parts[0].startswith("v") and parts[0][1:].isdigit():
        after_upload = parts[1]
    # Strip extension
    if "." in after_upload.rsplit("/", 1)[-1]:
        after_upload = after_upload.rsplit(".", 1)[0]
    return after_upload
