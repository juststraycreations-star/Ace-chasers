"""Swipes, likes, matches, friend-requests, and inbox routes.

A "social" graph of the user's interactions with other users. Kept together
because the friend-request / like / inbox logic shares quite a bit of
business logic (de-duping incoming likes vs friend requests, auto-friend on
mutual intent, etc.)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from deps import match_key, strip_private_fields, user_to_profile
from firebase_auth import get_current_user
from models import (
    FriendRequestOut,
    InboxOut,
    IncomingLikeOut,
    LikeOut,
    ProfileOut,
    SwipeIn,
)


router = APIRouter()


# --- Swipes & legacy likes/matches -----------------------------------------

@router.post("/api/swipes")
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
        reverse = await db.swipes.find_one(
            {"from_uid": payload.target_uid, "to_uid": current["uid"], "action": "like"}
        )
        if reverse:
            a, b = match_key(current["uid"], payload.target_uid)
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


@router.get("/api/likes", response_model=List[LikeOut])
async def list_likes(current=Depends(get_current_user)):
    db = get_db()
    swipes = await (
        db.swipes.find({"from_uid": current["uid"], "action": "like"})
        .sort("created_at", -1)
        .limit(200)
        .to_list(length=200)
    )
    target_uids = [s["to_uid"] for s in swipes]
    # Batch-fetch users + matches in one round-trip each. Exclude seeds +
    # incomplete profiles so the Likes list shows real users only.
    users_by_uid: dict[str, dict] = {}
    if target_uids:
        async for u in db.users.find(
            {
                "uid": {"$in": target_uids},
                "is_seed": {"$ne": True},
                "name": {"$nin": [None, ""]},
            }
        ):
            users_by_uid[u["uid"]] = u
    match_keys = [match_key(current["uid"], t) for t in target_uids]
    matches_by_key: dict[tuple[str, str], dict] = {}
    if match_keys:
        # Mongo can't easily query tuples; fetch all matches involving me.
        async for m in db.matches.find(
            {"$or": [{"user_a": current["uid"]}, {"user_b": current["uid"]}]}
        ):
            matches_by_key[(m["user_a"], m["user_b"])] = m

    out: list[LikeOut] = []
    for swipe in swipes:
        target = users_by_uid.get(swipe["to_uid"])
        if not target:
            continue
        key = match_key(current["uid"], swipe["to_uid"])
        match_doc = matches_by_key.get(key)
        friended = bool(match_doc and current["uid"] in (match_doc.get("friended_by") or []))
        out.append(
            LikeOut(
                player=user_to_profile(target),
                likedAt=swipe.get("created_at", ""),
                matched=match_doc is not None,
                friended=friended,
            )
        )
    return out


@router.post("/api/matches/{target_uid}/friend")
async def add_friend(target_uid: str, current=Depends(get_current_user)):
    db = get_db()
    a, b = match_key(current["uid"], target_uid)
    match = await db.matches.find_one({"user_a": a, "user_b": b})
    if not match:
        raise HTTPException(status_code=404, detail="No match exists with this user yet")
    await db.matches.update_one(
        {"user_a": a, "user_b": b},
        {"$addToSet": {"friended_by": current["uid"]}},
    )
    return {"ok": True}


@router.delete("/api/likes/{target_uid}")
async def remove_like(target_uid: str, current=Depends(get_current_user)):
    db = get_db()
    await db.swipes.delete_one(
        {"from_uid": current["uid"], "to_uid": target_uid, "action": "like"}
    )
    a, b = match_key(current["uid"], target_uid)
    await db.matches.delete_one({"user_a": a, "user_b": b})
    return {"ok": True}


@router.get("/api/friends", response_model=List[ProfileOut])
async def list_my_friends(current=Depends(get_current_user)):
    """All confirmed friends of the current user."""
    return await _friends_for(current["uid"])


@router.get("/api/users/{uid}/friends", response_model=List[ProfileOut])
async def list_user_friends(uid: str, current=Depends(get_current_user)):
    """Public friends list for any user (used by their public profile page)."""
    return await _friends_for(uid)


async def _friends_for(uid: str) -> list[ProfileOut]:
    db = get_db()
    matches = await db.matches.find(
        {"friended_by": uid},
        {"user_a": 1, "user_b": 1, "friended_by": 1, "_id": 0},
    ).limit(500).to_list(length=500)
    other_uids: list[str] = []
    for m in matches:
        friended = m.get("friended_by") or []
        other = m["user_b"] if m["user_a"] == uid else m["user_a"]
        if other in friended:
            other_uids.append(other)
    if not other_uids:
        return []
    users_by_uid: dict[str, dict] = {}
    async for u in db.users.find(
        {
            "uid": {"$in": other_uids},
            "is_seed": {"$ne": True},
            "name": {"$nin": [None, ""]},
        }
    ):
        users_by_uid[u["uid"]] = u
    out: list[ProfileOut] = []
    for ouid in other_uids:
        doc = users_by_uid.get(ouid)
        if not doc:
            continue
        prof = user_to_profile(doc)
        strip_private_fields(prof)
        prof.email = None
        prof.emailVerified = False
        out.append(prof)
    return out


@router.delete("/api/incoming-likes/{from_uid}")
async def ignore_incoming_like(from_uid: str, current=Depends(get_current_user)):
    """Hide an incoming like from your inbox. Deletes the sender's like row
    so it stops showing up under 'People who liked you'."""
    db = get_db()
    res = await db.swipes.delete_one(
        {"from_uid": from_uid, "to_uid": current["uid"], "action": "like"}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No incoming like from that user")
    return {"ok": True}


# --- Friend requests + inbox ------------------------------------------------

@router.post("/api/friend-requests/{target_uid}")
async def send_friend_request(target_uid: str, current=Depends(get_current_user)):
    """Send a friend request. Also records a 'like' swipe so the existing
    match flow still works. If the target already has a pending request out
    to me OR has already liked me, we auto-accept the friendship: a match is
    created with both users in `friended_by`."""
    db = get_db()
    if target_uid == current["uid"]:
        raise HTTPException(status_code=400, detail="Cannot friend yourself")
    target = await db.users.find_one({"uid": target_uid})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    now = datetime.now(timezone.utc).isoformat()

    await db.swipes.update_one(
        {"from_uid": current["uid"], "to_uid": target_uid},
        {"$set": {"from_uid": current["uid"], "to_uid": target_uid, "action": "like", "created_at": now}},
        upsert=True,
    )

    reverse_req = await db.friend_requests.find_one({"from_uid": target_uid, "to_uid": current["uid"]})
    reverse_like = await db.swipes.find_one(
        {"from_uid": target_uid, "to_uid": current["uid"], "action": "like"}
    )
    auto_accept = reverse_req is not None or reverse_like is not None

    if auto_accept:
        a, b = match_key(current["uid"], target_uid)
        await db.matches.update_one(
            {"user_a": a, "user_b": b},
            {
                "$setOnInsert": {"user_a": a, "user_b": b, "friended_by": [], "created_at": now},
            },
            upsert=True,
        )
        if reverse_req is not None:
            await db.matches.update_one(
                {"user_a": a, "user_b": b},
                {"$addToSet": {"friended_by": {"$each": [current["uid"], target_uid]}}},
            )
            await db.friend_requests.delete_one({"from_uid": target_uid, "to_uid": current["uid"]})
        else:
            await db.matches.update_one(
                {"user_a": a, "user_b": b},
                {"$addToSet": {"friended_by": current["uid"]}},
            )
        return {"ok": True, "matched": True, "friended": reverse_req is not None}

    await db.friend_requests.update_one(
        {"from_uid": current["uid"], "to_uid": target_uid},
        {"$set": {"from_uid": current["uid"], "to_uid": target_uid, "created_at": now}},
        upsert=True,
    )
    return {"ok": True, "matched": False, "friended": False}


@router.post("/api/friend-requests/{from_uid}/accept")
async def accept_friend_request(from_uid: str, current=Depends(get_current_user)):
    db = get_db()
    req = await db.friend_requests.find_one({"from_uid": from_uid, "to_uid": current["uid"]})
    if not req:
        raise HTTPException(status_code=404, detail="No pending request from that user")

    now = datetime.now(timezone.utc).isoformat()
    await db.swipes.update_one(
        {"from_uid": current["uid"], "to_uid": from_uid},
        {"$set": {"from_uid": current["uid"], "to_uid": from_uid, "action": "like", "created_at": now}},
        upsert=True,
    )

    a, b = match_key(current["uid"], from_uid)
    await db.matches.update_one(
        {"user_a": a, "user_b": b},
        {
            "$setOnInsert": {"user_a": a, "user_b": b, "friended_by": [], "created_at": now},
        },
        upsert=True,
    )
    await db.matches.update_one(
        {"user_a": a, "user_b": b},
        {"$addToSet": {"friended_by": {"$each": [current["uid"], from_uid]}}},
    )
    await db.friend_requests.delete_one({"from_uid": from_uid, "to_uid": current["uid"]})
    return {"ok": True}


@router.post("/api/friend-requests/{from_uid}/decline")
async def decline_friend_request(from_uid: str, current=Depends(get_current_user)):
    db = get_db()
    res = await db.friend_requests.delete_one({"from_uid": from_uid, "to_uid": current["uid"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No pending request from that user")
    return {"ok": True}


@router.get("/api/inbox", response_model=InboxOut)
async def get_inbox(current=Depends(get_current_user)):
    """Notifications surfaced to the caller: people who liked you (and you
    haven't liked them back) + pending friend requests sent to you."""
    db = get_db()
    me = current["uid"]

    # --- Pending friend requests to me (1 batch users query). -----------
    fr_docs = await (
        db.friend_requests.find({"to_uid": me})
        .sort("created_at", -1)
        .limit(200)
        .to_list(length=200)
    )
    fr_sender_uids = [r["from_uid"] for r in fr_docs]
    senders_by_uid: dict[str, dict] = {}
    if fr_sender_uids:
        # Real, completed-profile users only — exclude seeds + empty signups.
        async for u in db.users.find(
            {
                "uid": {"$in": fr_sender_uids},
                "is_seed": {"$ne": True},
                "name": {"$nin": [None, ""]},
            }
        ):
            senders_by_uid[u["uid"]] = u
    fr_out: list[FriendRequestOut] = []
    fr_from_uids: set[str] = set()
    for req in fr_docs:
        sender = senders_by_uid.get(req["from_uid"])
        if not sender:
            continue
        prof = user_to_profile(sender)
        strip_private_fields(prof)
        prof.email = None
        prof.emailVerified = False
        fr_out.append(FriendRequestOut(from_user=prof, created_at=req.get("created_at", "")))
        fr_from_uids.add(req["from_uid"])

    # --- Incoming likes (de-duped). One batch users query. -------------
    my_likes_cursor = db.swipes.find(
        {"from_uid": me, "action": "like"}, {"to_uid": 1, "_id": 0}
    ).limit(500)
    my_like_targets = {d["to_uid"] async for d in my_likes_cursor}

    incoming_swipes = await (
        db.swipes.find({"to_uid": me, "action": "like"})
        .sort("created_at", -1)
        .limit(200)
        .to_list(length=200)
    )
    relevant_swipes = [
        s for s in incoming_swipes
        if s["from_uid"] not in my_like_targets and s["from_uid"] not in fr_from_uids
    ]
    like_sender_uids = list({s["from_uid"] for s in relevant_swipes})
    like_senders_by_uid: dict[str, dict] = {}
    if like_sender_uids:
        async for u in db.users.find(
            {
                "uid": {"$in": like_sender_uids},
                "is_seed": {"$ne": True},
                "name": {"$nin": [None, ""]},
            }
        ):
            like_senders_by_uid[u["uid"]] = u
    likes_out: list[IncomingLikeOut] = []
    for swipe in relevant_swipes:
        sender = like_senders_by_uid.get(swipe["from_uid"])
        if not sender:
            continue
        prof = user_to_profile(sender)
        strip_private_fields(prof)
        prof.email = None
        prof.emailVerified = False
        likes_out.append(IncomingLikeOut(from_user=prof, liked_at=swipe.get("created_at", "")))

    sent_uids: list[str] = []
    async for d in db.friend_requests.find({"from_uid": me}, {"to_uid": 1}):
        sent_uids.append(d["to_uid"])

    friend_uids: list[str] = []
    async for m in db.matches.find({"friended_by": me}):
        friended = m.get("friended_by") or []
        other = m["user_b"] if m["user_a"] == me else m["user_a"]
        if other in friended:
            friend_uids.append(other)

    return InboxOut(
        incoming_likes=likes_out,
        incoming_friend_requests=fr_out,
        sent_friend_request_uids=sent_uids,
        friend_uids=friend_uids,
    )
