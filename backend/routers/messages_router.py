"""Direct messages between users.

Schema (`messages` collection):
  { id, pair_key (lo|hi), from_uid, to_uid, body, created_at, read }

`pair_key` is the sorted "lo|hi" UID tuple so a single index covers fetching
the thread for either side of the conversation.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from deps import match_key, strip_private_fields, user_to_profile
from firebase_auth import get_current_user
from models import ProfileOut


router = APIRouter()


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: str
    from_uid: str
    to_uid: str
    body: str
    created_at: str
    is_mine: bool = False


class ThreadOut(BaseModel):
    with_user: ProfileOut
    last_message: str
    last_at: str
    unread: int


def _pair_key(a: str, b: str) -> str:
    lo, hi = match_key(a, b)
    return f"{lo}|{hi}"


@router.get("/api/messages/threads", response_model=list[ThreadOut])
async def list_threads(current=Depends(get_current_user)):
    """Distinct conversations involving the caller, newest first."""
    db = get_db()
    me = current["uid"]
    pipeline = [
        {"$match": {"$or": [{"from_uid": me}, {"to_uid": me}]}},
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$pair_key",
                "last_message": {"$first": "$body"},
                "last_at": {"$first": "$created_at"},
                "last_from": {"$first": "$from_uid"},
                "last_to": {"$first": "$to_uid"},
                "unread": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$eq": ["$to_uid", me]},
                                    {"$ne": [{"$ifNull": ["$read", False]}, True]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {"$sort": {"last_at": -1}},
        {"$limit": 200},
    ]
    rows = await db.messages.aggregate(pipeline).to_list(length=200)
    if not rows:
        return []
    other_uids = [
        (r["last_to"] if r["last_from"] == me else r["last_from"]) for r in rows
    ]
    users_by_uid: dict[str, dict] = {}
    async for u in db.users.find({"uid": {"$in": other_uids}}):
        users_by_uid[u["uid"]] = u

    out: list[ThreadOut] = []
    for r in rows:
        other = r["last_to"] if r["last_from"] == me else r["last_from"]
        doc = users_by_uid.get(other)
        if not doc:
            continue
        prof = user_to_profile(doc)
        strip_private_fields(prof)
        prof.email = None
        prof.emailVerified = False
        out.append(
            ThreadOut(
                with_user=prof,
                last_message=r["last_message"],
                last_at=r["last_at"],
                unread=r["unread"],
            )
        )
    return out


@router.get("/api/messages/{other_uid}", response_model=list[MessageOut])
async def get_thread(other_uid: str, current=Depends(get_current_user)):
    """Return all messages between caller and the other user, oldest first.
    Marks the caller's inbound messages from that user as read."""
    db = get_db()
    me = current["uid"]
    pk = _pair_key(me, other_uid)
    msgs = await (
        db.messages.find({"pair_key": pk})
        .sort("created_at", 1)
        .limit(500)
        .to_list(length=500)
    )
    # Mark messages from other_uid -> me as read.
    await db.messages.update_many(
        {"pair_key": pk, "from_uid": other_uid, "to_uid": me, "read": {"$ne": True}},
        {"$set": {"read": True}},
    )
    return [
        MessageOut(
            id=m["id"],
            from_uid=m["from_uid"],
            to_uid=m["to_uid"],
            body=m["body"],
            created_at=m["created_at"],
            is_mine=m["from_uid"] == me,
        )
        for m in msgs
    ]


@router.post("/api/messages/{other_uid}", response_model=MessageOut)
async def send_message(
    other_uid: str, payload: MessageIn, current=Depends(get_current_user)
):
    db = get_db()
    me = current["uid"]
    if other_uid == me:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    target = await db.users.find_one({"uid": other_uid})
    if not target:
        raise HTTPException(status_code=404, detail="Recipient not found")
    doc = {
        "id": secrets.token_urlsafe(12),
        "pair_key": _pair_key(me, other_uid),
        "from_uid": me,
        "to_uid": other_uid,
        "body": payload.body.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read": False,
    }
    await db.messages.insert_one(doc)
    return MessageOut(
        id=doc["id"],
        from_uid=me,
        to_uid=other_uid,
        body=doc["body"],
        created_at=doc["created_at"],
        is_mine=True,
    )
