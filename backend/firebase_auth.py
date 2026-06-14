"""Firebase Admin initialization + token verification dependency.

When a service-account JSON path is provided via FIREBASE_SERVICE_ACCOUNT_JSON
the backend uses firebase-admin to fully verify ID tokens.

If no service account is configured the backend falls back to an "insecure dev"
mode: it decodes the JWT without signature verification just to extract
`sub`/`uid`/`email`. This lets the app run end-to-end before the user has
supplied credentials. **Do not deploy without a service account.**
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

logger = logging.getLogger("firebase_auth")

_FIREBASE_READY = False

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth_admin
    from firebase_admin import credentials as firebase_credentials
except Exception:  # pragma: no cover - import-time guard
    firebase_admin = None  # type: ignore
    firebase_auth_admin = None  # type: ignore
    firebase_credentials = None  # type: ignore


def init_firebase() -> bool:
    """Initialize firebase-admin from FIREBASE_SERVICE_ACCOUNT_JSON if set."""
    global _FIREBASE_READY
    if _FIREBASE_READY:
        return True
    if firebase_admin is None:
        return False

    sa_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_path:
        logger.warning(
            "FIREBASE_SERVICE_ACCOUNT_JSON not set — running in INSECURE DEV "
            "MODE (tokens decoded without verification). Set ENV=prod to "
            "disable this fallback."
        )
        return False

    # If an admin path is configured but unreadable, fail hard rather than
    # silently dropping into insecure-decode mode.
    if not os.path.exists(sa_path):
        raise RuntimeError(
            f"FIREBASE_SERVICE_ACCOUNT_JSON points to {sa_path!r} but the file "
            f"does not exist. Refusing to start to avoid silent insecure-decode."
        )

    try:
        if not firebase_admin._apps:
            cred = firebase_credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
        _FIREBASE_READY = True
        logger.info("firebase-admin initialized from %s", sa_path)
        return True
    except Exception as exc:
        # Service account configured but failed to load — also fail hard.
        raise RuntimeError(f"Failed to init firebase-admin from {sa_path}: {exc}") from exc


def _decode_unverified(token: str) -> dict:
    """Decode the JWT payload without verifying signature (dev mode only)."""
    if os.environ.get("ENV", "").lower() in {"prod", "production"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured: refusing to accept unverified tokens in production.",
        )
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


def verify_token(token: str) -> dict:
    """Return the decoded claims for a Firebase ID token."""
    if init_firebase():
        try:
            return firebase_auth_admin.verify_id_token(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Firebase token verification failed: {exc}",
            )
    return _decode_unverified(token)


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """FastAPI dependency that returns the Firebase claims for the caller."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = verify_token(token)
    uid = claims.get("uid") or claims.get("user_id") or claims.get("sub")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing uid/sub claim",
        )
    return {
        "uid": uid,
        "email": claims.get("email"),
        "name": claims.get("name") or claims.get("display_name"),
        "picture": claims.get("picture"),
        "claims": claims,
    }
