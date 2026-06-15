"""Ace Chasers backend API.

All app routes are prefixed with /api and protected by `get_current_user`
(Firebase ID token via Authorization: Bearer). Endpoints:

  POST /api/auth/sync       Upsert the user record for the caller, then ensure
                            inbound demo likes exist (for matched-likes demo).
  GET  /api/users/me        Return the caller's profile.
  PUT  /api/users/me        Update the caller's profile.
  GET  /api/discovery       List candidate players to swipe on (excludes the
                            caller and anyone already swiped).
  POST /api/swipes          Body: {target_uid, action: like|pass}. Records the
                            swipe and, on a mutual like, creates a Match.
  GET  /api/likes           List profiles the caller has liked + match state.
  POST /api/matches/{uid}/friend   Mark a match as friended.
  DELETE /api/likes/{uid}   Remove a like (and any related match).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Literal, Optional

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from db import (  # noqa: E402  (load_dotenv must run first)
    ensure_indexes,
    ensure_inbound_likes_for,
    get_db,
    seed_demo_users,
)
from firebase_auth import get_current_user, init_firebase  # noqa: E402
from invites import (  # noqa: E402
    create_invite,
    list_invites,
    redeem_invite,
    revoke_invite,
)
from posts import (  # noqa: E402
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    MIME_TO_EXT,
    UPLOAD_DIR,
    create_post,
    delete_post,
    ensure_indexes as ensure_post_indexes,
    get_latest_public_post,
    list_feed,
    sniff_image_mime,
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

# Serve user-uploaded images. Files are stored at /app/backend/uploads/.
app.mount("/api/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# --- Models -----------------------------------------------------------------

class ProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    age: Optional[int] = Field(default=None, ge=13, le=120)
    skillLevel: Optional[str] = Field(default=None, max_length=20)
    location: Optional[str] = Field(default=None, max_length=120)
    favoriteCourse: Optional[str] = Field(default=None, max_length=120)
    favoriteFrisbee: Optional[str] = Field(default=None, max_length=120)
    homeCourse: Optional[str] = Field(default=None, max_length=120)
    bio: Optional[str] = Field(default=None, max_length=1000)
    interests: Optional[List[str]] = Field(default=None, max_length=20)
    profilePictureUrl: Optional[str] = Field(default=None, max_length=500)
    bannerUrl: Optional[str] = Field(default=None, max_length=500)
    privacy: Optional[dict] = None  # {favoriteFrisbee, favoriteCourse, homeCourse} -> bool (True = private)


class AuthSyncIn(BaseModel):
    invite_code: Optional[str] = None


class InviteCreateIn(BaseModel):
    email: Optional[str] = None
    expires_at: Optional[str] = None


class ProfileOut(BaseModel):
    uid: str
    email: Optional[str] = None
    emailVerified: bool = False
    name: Optional[str] = None
    age: Optional[int] = None
    skillLevel: Optional[str] = None
    location: Optional[str] = None
    favoriteCourse: Optional[str] = None
    favoriteFrisbee: Optional[str] = None
    bio: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    profilePictureUrl: Optional[str] = None
    bannerUrl: Optional[str] = None
    homeCourse: Optional[str] = None
    privacy: dict = Field(default_factory=dict)


class SwipeIn(BaseModel):
    target_uid: str
    action: Literal["like", "pass"]


class LikeOut(BaseModel):
    player: ProfileOut
    likedAt: str
    matched: bool
    friended: bool


class PostAuthor(BaseModel):
    uid: str
    name: Optional[str] = None
    profilePictureUrl: Optional[str] = None


class RecentPost(BaseModel):
    id: str
    body: str
    created_at: str
    has_image: bool = False


class DiscoveryProfile(ProfileOut):
    """ProfileOut + the player's most recent public post (if any)."""
    recent_post: Optional[RecentPost] = None


class PostOut(BaseModel):
    id: str
    body: str
    image_url: Optional[str] = None
    visibility: Literal["public", "friends_only"]
    created_at: str
    author: PostAuthor
    is_mine: bool = False


# --- Helpers ----------------------------------------------------------------

def _user_to_profile(doc: dict, *, email_verified: Optional[bool] = None) -> ProfileOut:
    return ProfileOut(
        uid=doc["uid"],
        email=doc.get("email"),
        emailVerified=bool(email_verified if email_verified is not None else doc.get("email_verified", False)),
        name=doc.get("name"),
        age=doc.get("age"),
        skillLevel=doc.get("skillLevel"),
        location=doc.get("location"),
        favoriteCourse=doc.get("favoriteCourse"),
        favoriteFrisbee=doc.get("favoriteFrisbee"),
        bio=doc.get("bio"),
        interests=doc.get("interests") or [],
        profilePictureUrl=doc.get("profilePictureUrl"),
        bannerUrl=doc.get("bannerUrl"),
    )


def _match_key(a: str, b: str) -> tuple[str, str]:
    """Canonical (low, high) ordering so the unique index works regardless of
    who liked first."""
    return (a, b) if a < b else (b, a)


def _require_invite_enabled() -> bool:
    return os.environ.get("REQUIRE_INVITE", "false").strip().lower() in {"1", "true", "yes"}


def _claims_email_verified(claims: dict) -> bool:
    # Firebase Admin returns `email_verified`. Our dev path may set the same.
    if "email_verified" in claims:
        return bool(claims["email_verified"])
    # Dev fallback: no info → treat as verified so devs aren't blocked by
    # the banner. Real deployments always have the field.
    return True


async def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> bool:
    expected = os.environ.get("ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return True


# --- Lifecycle --------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    init_firebase()
    await ensure_indexes()
    await ensure_post_indexes()
    await seed_demo_users()


# --- Routes -----------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    """Public config consumed by the frontend on app load."""
    return {"require_invite": _require_invite_enabled()}


@app.post("/api/auth/sync", response_model=ProfileOut)
async def auth_sync(
    payload: AuthSyncIn = Body(default_factory=AuthSyncIn),
    current=Depends(get_current_user),
):
    """Idempotently upsert the user record for the caller. New users may need
    to redeem an invite code when REQUIRE_INVITE is enabled. Existing users
    always pass through (no retroactive gating)."""
    db = get_db()
    existing = await db.users.find_one({"uid": current["uid"]})
    is_new_user = existing is None

    if is_new_user and _require_invite_enabled():
        await redeem_invite(
            code=(payload.invite_code or "").strip(),
            uid=current["uid"],
            email=current.get("email"),
        )

    now = datetime.now(timezone.utc).isoformat()
    email_verified = _claims_email_verified(current.get("claims") or {})
    update = {
        "$setOnInsert": {
            "uid": current["uid"],
            "created_at": now,
            "is_seed": False,
            "interests": ["casual play"],
            "skillLevel": "Beginner",
            "bio": "New to Ace Chasers!",
        },
        "$set": {
            "email": current.get("email"),
            "email_verified": email_verified,
            "updated_at": now,
        },
    }
    if current.get("name"):
        update["$setOnInsert"]["name"] = current["name"]
    if current.get("picture"):
        update["$setOnInsert"]["profilePictureUrl"] = current["picture"]

    await db.users.update_one({"uid": current["uid"]}, update, upsert=True)
    await ensure_inbound_likes_for(current["uid"])

    doc = await db.users.find_one({"uid": current["uid"]})
    return _user_to_profile(doc, email_verified=email_verified)


@app.get("/api/users/me", response_model=ProfileOut)
async def get_me(current=Depends(get_current_user)):
    db = get_db()
    doc = await db.users.find_one({"uid": current["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found — call /api/auth/sync first")
    email_verified = _claims_email_verified(current.get("claims") or {})
    return _user_to_profile(doc, email_verified=email_verified)


@app.get("/api/users/{uid}", response_model=ProfileOut)
async def get_user_by_uid(uid: str, current=Depends(get_current_user)):
    """Public profile view of any user. Email is stripped unless it's the
    caller's own record. Fields marked private in the user's `privacy` map
    are also stripped for non-self queries."""
    db = get_db()
    doc = await db.users.find_one({"uid": uid})
    if not doc:
        raise HTTPException(status_code=404, detail="Player not found")
    is_self = uid == current["uid"]
    profile = _user_to_profile(doc)
    if not is_self:
        profile.email = None
        profile.emailVerified = False
        _strip_private_fields(profile)
    return profile


# --- Admin: invitations -----------------------------------------------------

@app.get("/api/admin/invites")
async def admin_list_invites(_: bool = Depends(require_admin)):
    return await list_invites()


@app.post("/api/admin/invites")
async def admin_create_invite(payload: InviteCreateIn, _: bool = Depends(require_admin)):
    return await create_invite(email=payload.email, expires_at=payload.expires_at)


@app.delete("/api/admin/invites/{code}")
async def admin_revoke_invite(code: str, _: bool = Depends(require_admin)):
    ok = await revoke_invite(code)
    if not ok:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"ok": True}


@app.put("/api/users/me", response_model=ProfileOut)
async def update_me(payload: ProfileIn, current=Depends(get_current_user)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"uid": current["uid"]}, {"$set": updates}, upsert=True)
    doc = await db.users.find_one({"uid": current["uid"]})
    return _user_to_profile(doc, email_verified=_claims_email_verified(current.get("claims") or {}))


async def _save_image_for_user(image: UploadFile, uid: str, prefix: str) -> str:
    """Validate by sniffing magic bytes, persist to UPLOAD_DIR with a
    server-controlled filename + extension, return the public URL path."""
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")
    real_mime = sniff_image_mime(data)
    if real_mime is None:
        raise HTTPException(status_code=400, detail="File is not a supported image (jpeg/png/webp/gif)")
    ext = MIME_TO_EXT[real_mime]
    safe_uid = uid.replace("/", "_")
    filename = f"{prefix}-{safe_uid}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}.{ext}"
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(data)
    return f"/api/uploads/{filename}"


@app.post("/api/users/me/profile-picture", response_model=ProfileOut)
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
    return _user_to_profile(doc, email_verified=_claims_email_verified(current.get("claims") or {}))


@app.post("/api/users/me/banner", response_model=ProfileOut)
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
    return _user_to_profile(doc, email_verified=_claims_email_verified(current.get("claims") or {}))


@app.get("/api/discovery", response_model=List[DiscoveryProfile])
async def discovery(current=Depends(get_current_user)):
    db = get_db()
    # Players already swiped on by the caller
    swiped_cursor = db.swipes.find({"from_uid": current["uid"]}, {"to_uid": 1})
    swiped_uids = [d["to_uid"] async for d in swiped_cursor]
    exclude = set(swiped_uids + [current["uid"]])

    cursor = db.users.find({"uid": {"$nin": list(exclude)}}).limit(50)
    out: list[DiscoveryProfile] = []
    async for doc in cursor:
        base = _user_to_profile(doc)
        _strip_private_fields(base)
        post = await get_latest_public_post(doc["uid"])
        recent = None
        if post:
            recent = RecentPost(
                id=post["id"],
                body=post.get("body") or "",
                created_at=post.get("created_at") or "",
                has_image=bool(post.get("image_path")),
            )
        out.append(DiscoveryProfile(**base.model_dump(), recent_post=recent))
    return out


@app.post("/api/swipes")
async def post_swipe(payload: SwipeIn, current=Depends(get_current_user)):
    db = get_db()
    if payload.target_uid == current["uid"]:
        raise HTTPException(status_code=400, detail="Cannot swipe on yourself")

    target = await db.users.find_one({"uid": payload.target_uid})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.swipes.update_one(
        {"from_uid": current["uid"], "to_uid": payload.target_uid},
        {
            "$set": {
                "from_uid": current["uid"],
                "to_uid": payload.target_uid,
                "action": payload.action,
                "created_at": now,
            }
        },
        upsert=True,
    )

    matched = False
    if payload.action == "like":
        # Did the target previously like the caller? -> match
        reverse = await db.swipes.find_one(
            {"from_uid": payload.target_uid, "to_uid": current["uid"], "action": "like"}
        )
        if reverse:
            a, b = _match_key(current["uid"], payload.target_uid)
            await db.matches.update_one(
                {"user_a": a, "user_b": b},
                {
                    "$setOnInsert": {
                        "user_a": a,
                        "user_b": b,
                        "friended_by": [],
                        "created_at": now,
                    }
                },
                upsert=True,
            )
            matched = True

    return {"ok": True, "matched": matched}


@app.get("/api/likes", response_model=List[LikeOut])
async def list_likes(current=Depends(get_current_user)):
    db = get_db()
    cursor = db.swipes.find({"from_uid": current["uid"], "action": "like"}).sort("created_at", -1).limit(200)
    out: list[LikeOut] = []
    async for swipe in cursor:
        target = await db.users.find_one({"uid": swipe["to_uid"]})
        if not target:
            continue
        a, b = _match_key(current["uid"], swipe["to_uid"])
        match_doc = await db.matches.find_one({"user_a": a, "user_b": b})
        friended = bool(match_doc and current["uid"] in (match_doc.get("friended_by") or []))
        out.append(
            LikeOut(
                player=_user_to_profile(target),
                likedAt=swipe.get("created_at", ""),
                matched=match_doc is not None,
                friended=friended,
            )
        )
    return out


@app.post("/api/matches/{target_uid}/friend")
async def add_friend(target_uid: str, current=Depends(get_current_user)):
    db = get_db()
    a, b = _match_key(current["uid"], target_uid)
    match = await db.matches.find_one({"user_a": a, "user_b": b})
    if not match:
        raise HTTPException(status_code=404, detail="No match exists with this user yet")
    await db.matches.update_one(
        {"user_a": a, "user_b": b},
        {"$addToSet": {"friended_by": current["uid"]}},
    )
    return {"ok": True}


@app.delete("/api/likes/{target_uid}")
async def remove_like(target_uid: str, current=Depends(get_current_user)):
    db = get_db()
    await db.swipes.delete_one(
        {"from_uid": current["uid"], "to_uid": target_uid, "action": "like"}
    )
    a, b = _match_key(current["uid"], target_uid)
    await db.matches.delete_one({"user_a": a, "user_b": b})
    return {"ok": True}


# --- Feed / Posts -----------------------------------------------------------

POST_BODY_MAX = 1000


async def _hydrate_post(post: dict, viewer_uid: str) -> PostOut:
    db = get_db()
    author = await db.users.find_one({"uid": post["author_uid"]})
    author_obj = PostAuthor(
        uid=post["author_uid"],
        name=(author or {}).get("name"),
        profilePictureUrl=(author or {}).get("profilePictureUrl"),
    )
    image_url = None
    if post.get("image_path"):
        # image_path stored as plain filename; expose via /api/uploads/<file>.
        image_url = f"/api/uploads/{post['image_path']}"
    return PostOut(
        id=post["id"],
        body=post.get("body", ""),
        image_url=image_url,
        visibility=post.get("visibility", "public"),
        created_at=post.get("created_at", ""),
        author=author_obj,
        is_mine=post["author_uid"] == viewer_uid,
    )


FEED_PAGE_SIZE = 20


@app.get("/api/feed")
async def get_feed(
    before: Optional[str] = None,
    limit: int = FEED_PAGE_SIZE,
    current=Depends(get_current_user),
):
    """Cursor-paginated feed. `before` is the ISO `created_at` of the last
    item from the previous page; omit on first call. Response shape:
    `{ posts, next_cursor }` where `next_cursor` is null when there are no
    more posts."""
    limit = max(1, min(limit, 50))
    raw_posts = await list_feed(current["uid"], limit=limit, before=before)
    hydrated = [await _hydrate_post(p, current["uid"]) for p in raw_posts]
    next_cursor = raw_posts[-1]["created_at"] if len(raw_posts) == limit else None
    return {"posts": hydrated, "next_cursor": next_cursor}


@app.post("/api/posts", response_model=PostOut)
async def create_post_endpoint(
    body: str = Form(""),
    visibility: Literal["public", "friends_only"] = Form("public"),
    image: Optional[UploadFile] = File(default=None),
    current=Depends(get_current_user),
):
    body = (body or "").strip()
    if not body and image is None:
        raise HTTPException(status_code=400, detail="Post must include text or an image")
    if len(body) > POST_BODY_MAX:
        raise HTTPException(status_code=400, detail=f"Post text capped at {POST_BODY_MAX} characters")

    image_filename: Optional[str] = None
    if image is not None and image.filename:
        data = await image.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")
        real_mime = sniff_image_mime(data)
        if real_mime is None:
            raise HTTPException(status_code=400, detail="File is not a supported image (jpeg/png/webp/gif)")
        ext = MIME_TO_EXT[real_mime]
        image_filename = f"{current['uid'].replace('/', '_')}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}.{ext}"
        dest = os.path.join(UPLOAD_DIR, image_filename)
        with open(dest, "wb") as f:
            f.write(data)

    post = await create_post(
        author_uid=current["uid"],
        body=body,
        visibility=visibility,
        image_path=image_filename,
    )
    return await _hydrate_post(post, current["uid"])


@app.delete("/api/posts/{post_id}")
async def delete_post_endpoint(post_id: str, current=Depends(get_current_user)):
    ok = await delete_post(post_id, current["uid"])
    if not ok:
        raise HTTPException(status_code=404, detail="Post not found or not yours")
    return {"ok": True}
