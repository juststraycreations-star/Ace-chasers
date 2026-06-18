"""Shared helper functions used across routers."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException

from models import ProfileOut


PRIVATE_FIELDS = ("favoriteFrisbee", "favoriteCourse", "homeCourse", "location")


def user_to_profile(doc: dict, *, email_verified: Optional[bool] = None) -> ProfileOut:
    return ProfileOut(
        uid=doc["uid"],
        email=doc.get("email"),
        emailVerified=bool(
            email_verified if email_verified is not None else doc.get("email_verified", False)
        ),
        name=doc.get("name"),
        age=doc.get("age"),
        skillLevel=doc.get("skillLevel"),
        location=doc.get("location"),
        favoriteCourse=doc.get("favoriteCourse"),
        favoriteFrisbee=doc.get("favoriteFrisbee"),
        homeCourse=doc.get("homeCourse"),
        bio=doc.get("bio"),
        interests=doc.get("interests") or [],
        profilePictureUrl=doc.get("profilePictureUrl"),
        bannerUrl=doc.get("bannerUrl"),
        privacy=doc.get("privacy") or {},
    )


def strip_private_fields(profile: ProfileOut) -> ProfileOut:
    """Null out any field flagged True in the user's privacy map. Mutates +
    returns the same instance. Use when serving a profile to anyone other
    than its owner."""
    privacy = profile.privacy or {}
    for field in PRIVATE_FIELDS:
        if privacy.get(field):
            setattr(profile, field, None)
    return profile


def match_key(a: str, b: str) -> tuple[str, str]:
    """Canonical (low, high) ordering so the unique index works regardless of
    who liked first."""
    return (a, b) if a < b else (b, a)


def require_invite_enabled() -> bool:
    return os.environ.get("REQUIRE_INVITE", "false").strip().lower() in {"1", "true", "yes"}


def claims_email_verified(claims: dict) -> bool:
    if "email_verified" in claims:
        return bool(claims["email_verified"])
    # Dev fallback: no info → treat as verified so devs aren't blocked.
    return True


async def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> bool:
    expected = os.environ.get("ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return True
