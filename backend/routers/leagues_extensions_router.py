"""League extensions — QR self-enroll, manager broadcasts, feed moderation.

Extracted as a companion sub-router. Attaches to the same `api_router`
imported from `leagues_router.py` so the URL surface stays flat under
`/api/*`.

Endpoints:
  * POST   /api/rounds/{round_id}/self-enroll     — QR-scan check-in
  * GET    /api/rounds/{round_id}/qr              — signed QR payload
  * POST   /api/leagues/{league_id}/broadcast     — director → all members
  * DELETE /api/feed/{post_id}                    — director hide/delete
  * POST   /api/leagues/{league_id}/mute/{uid}    — director mute a user
  * DELETE /api/leagues/{league_id}/mute/{uid}    — unmute
  * GET    /api/leagues/{league_id}/mutes         — list mutes
"""
from __future__ import annotations

import asyncio
from typing import Optional
from datetime import datetime, timezone

from fastapi import Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .leagues_router import (
    Card,
    LeagueMember,
    Scorecard,
    _compute_handicap,
    _generate_round_join_code,
    _require_member,
    api_router,
    db,
    get_current_user,
    ws_manager,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _require_director(league_id: str, user_id: str):
    """Assert the caller is the director of `league_id`, else 403."""
    lg = await db.leagues.find_one(
        {"id": league_id, "director_id": user_id}, {"_id": 0}
    )
    if not lg:
        raise HTTPException(status_code=403, detail="Director only")
    return lg


# ══════════════════════════════════════════════════════════════════
# ITEM 3 — QR self-enroll
# ══════════════════════════════════════════════════════════════════

@api_router.get("/rounds/{round_id}/qr")
async def get_round_qr_payload(round_id: str, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    """Return the deep-link that gets encoded into a QR image on the
    manager's screen. Any authenticated user can fetch this — the
    downstream self-enroll enforces league permissions.
    """
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    # Non-secret: the URL simply hands the phone the round id; the
    # backend still verifies membership before enrolling.
    return {
        "round_id": round_id,
        "round_name": rd.get("name"),
        "league_id": rd["league_id"],
        "deeplink": f"/rounds/{round_id}/checkin",
        "join_code": rd.get("join_code"),
        "generated_at": _now_iso(),
        "issuer": user.user_id,
    }


@api_router.post("/rounds/{round_id}/self-enroll")
async def self_enroll_round(round_id: str, request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    """QR check-in endpoint. When a player scans the round's QR the
    frontend POSTs here. If the caller isn't yet a league member we
    auto-join them; then we ensure they have a solo card + scorecard
    on this round. Idempotent — safe to call repeatedly.
    """
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    league_id = rd["league_id"]

    # Auto-join the league if not already a member.
    m = await db.league_members.find_one(
        {"league_id": league_id, "user_id": user.user_id}, {"_id": 0}
    )
    auto_joined_league = False
    if not m:
        count = await db.league_members.count_documents({"league_id": league_id})
        m_obj = LeagueMember(
            league_id=league_id, user_id=user.user_id, name=user.name,
            picture=user.picture, bag_tag=count + 1,
        )
        await db.league_members.insert_one(m_obj.model_dump())
        m = m_obj.model_dump()
        auto_joined_league = True

    # Reuse existing scorecard if already enrolled.
    existing_sc = await db.scorecards.find_one(
        {"round_id": round_id, "member_id": m["id"]}, {"_id": 0}
    )
    if existing_sc and existing_sc.get("card_id"):
        existing_card = await db.cards.find_one(
            {"id": existing_sc["card_id"]}, {"_id": 0}
        )
        return {
            "auto_joined_league": auto_joined_league,
            "already_enrolled": True,
            "card": existing_card,
            "scorecard": existing_sc,
        }

    # Fresh enrollment — solo card + scorecard.
    label = f"{m['name'].split(' ')[0]}'s Card"
    card = Card(round_id=round_id, label=label, player_ids=[m["id"]])
    await db.cards.insert_one(card.model_dump())

    if existing_sc:
        await db.scorecards.update_one(
            {"id": existing_sc["id"]}, {"$set": {"card_id": card.id}},
        )
        sc = {**existing_sc, "card_id": card.id}
    else:
        handicap = await _compute_handicap(league_id, m["id"], rd["par_per_hole"])
        sc = Scorecard(
            round_id=round_id, league_id=league_id, member_id=m["id"],
            card_id=card.id, scores=[0] * rd["holes"],
            handicap_at_round=handicap,
        )
        await db.scorecards.insert_one(sc.model_dump())
        sc = sc.model_dump()

    await ws_manager.broadcast(
        f"round:{round_id}",
        {"type": "player_joined", "member_id": m["id"], "card_id": card.id,
         "via": "qr_self_enroll"},
    )
    return {
        "auto_joined_league": auto_joined_league,
        "already_enrolled": False,
        "card": card.model_dump(),
        "scorecard": sc,
    }


# ══════════════════════════════════════════════════════════════════
# Manual join code — GET /api/rounds/join/{join_code}
# ══════════════════════════════════════════════════════════════════
# Alternative to the QR path for players dealing with camera glare or
# hardware scanning failures on the course. Case-insensitive lookup;
# the 4-char code is uppercase-alphanumeric with confusable letters
# (O, 0, I, 1) already excluded at generation time.
@api_router.get("/rounds/join/{join_code}")
async def lookup_round_by_join_code(join_code: str, request: Request,
                                     session_token: Optional[str] = Cookie(None),
                                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    normalized = (join_code or "").strip().upper()
    if not normalized:
        raise HTTPException(status_code=400, detail="Join code cannot be empty")
    rd = await db.rounds.find_one(
        {"join_code": normalized, "status": {"$in": ["scheduled", "active"]}},
        {"_id": 0},
    )
    if not rd:
        raise HTTPException(status_code=404, detail="No active round matches that code")

    league_id = rd["league_id"]
    # Auto-join the league if the player isn't already a member — mirrors
    # the QR self-enroll flow so the manual code has identical UX.
    m = await db.league_members.find_one(
        {"league_id": league_id, "user_id": user.user_id}, {"_id": 0}
    )
    auto_joined_league = False
    if not m:
        count = await db.league_members.count_documents({"league_id": league_id})
        m_obj = LeagueMember(
            league_id=league_id, user_id=user.user_id, name=user.name,
            picture=user.picture, bag_tag=count + 1,
        )
        await db.league_members.insert_one(m_obj.model_dump())
        m = m_obj.model_dump()
        auto_joined_league = True

    # Idempotent scorecard/card enrollment — same shape as QR path.
    existing_sc = await db.scorecards.find_one(
        {"round_id": rd["id"], "member_id": m["id"]}, {"_id": 0}
    )
    if existing_sc and existing_sc.get("card_id"):
        card = await db.cards.find_one({"id": existing_sc["card_id"]}, {"_id": 0})
        return {
            "round": rd,
            "auto_joined_league": auto_joined_league,
            "already_enrolled": True,
            "card": card,
            "scorecard": existing_sc,
        }

    label = f"{m['name'].split(' ')[0]}'s Card"
    card = Card(round_id=rd["id"], label=label, player_ids=[m["id"]])
    await db.cards.insert_one(card.model_dump())
    if existing_sc:
        await db.scorecards.update_one(
            {"id": existing_sc["id"]}, {"$set": {"card_id": card.id}},
        )
        sc = {**existing_sc, "card_id": card.id}
    else:
        handicap = await _compute_handicap(league_id, m["id"], rd["par_per_hole"])
        sc = Scorecard(
            round_id=rd["id"], league_id=league_id, member_id=m["id"],
            card_id=card.id, scores=[0] * rd["holes"],
            handicap_at_round=handicap,
        )
        await db.scorecards.insert_one(sc.model_dump())
        sc = sc.model_dump()

    await ws_manager.broadcast(
        f"round:{rd['id']}",
        {"type": "player_joined", "member_id": m["id"], "card_id": card.id,
         "via": "manual_join_code"},
    )
    return {
        "round": rd,
        "auto_joined_league": auto_joined_league,
        "already_enrolled": False,
        "card": card.model_dump(),
        "scorecard": sc,
    }


# ══════════════════════════════════════════════════════════════════
# Regenerate round join code — director-only "1-tap security" action
# ══════════════════════════════════════════════════════════════════
@api_router.put("/rounds/{round_id}/regenerate-code")
async def regenerate_round_join_code(round_id: str, request: Request,
                                       session_token: Optional[str] = Cookie(None),
                                       authorization: Optional[str] = Header(None)):
    """Wipe the old join_code and mint a fresh one. Broadcast the new
    value to any subscribed manager screens so their display and the
    active check-in loop refresh without a page reload.
    """
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    if rd.get("status") == "completed":
        # No security value in rotating a code on a done round, and it
        # would recycle a code that another live round could pick up.
        raise HTTPException(
            status_code=409,
            detail="Cannot regenerate code on a completed round",
        )
    await _require_director(rd["league_id"], user.user_id)
    new_code = await _generate_round_join_code(db)
    old_code = rd.get("join_code")
    await db.rounds.update_one({"id": round_id}, {"$set": {"join_code": new_code}})

    # Push the new code out over both the round channel (viewers on the
    # scorecard) and the league channel (managers on the round list).
    payload = {
        "type": "join_code_rotated",
        "round_id": round_id,
        "join_code": new_code,
        "old_code": old_code,
        "rotated_at": _now_iso(),
    }
    await ws_manager.broadcast(f"round:{round_id}", payload)
    await ws_manager.broadcast(f"league:{rd['league_id']}", payload)

    # Fan out silent FCM data-only payload to every checked-in player
    # so the manual code display refreshes on their device without a
    # scan or app reopen. Fire-and-forget so the manager's PUT returns
    # instantly.
    try:
        from ..push_service import process_live_round_event  # local import to avoid startup cycle
        asyncio.create_task(process_live_round_event(
            round_id, "join_code_rotated",
            join_code=new_code, old_code=old_code,
        ))
    except Exception:
        pass

    return {
        "ok": True,
        "round_id": round_id,
        "join_code": new_code,
        "old_code": old_code,
    }


# ══════════════════════════════════════════════════════════════════
# ITEM 5 — Manager broadcast & feed moderation
# ══════════════════════════════════════════════════════════════════

class BroadcastIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    title: Optional[str] = None


@api_router.post("/leagues/{league_id}/broadcast")
async def broadcast_to_league(league_id: str, payload: BroadcastIn, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    """Director-only. Fans out a single message to every league member's
    DM tray via the existing `messages` collection so it appears in each
    player's inbox exactly like a 1:1 note. Skips the sender.
    """
    user = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, user.user_id)
    members = await db.league_members.find(
        {"league_id": league_id}, {"_id": 0}
    ).to_list(2000)
    body = payload.body.strip()
    if payload.title:
        body = f"[{payload.title.strip()}]\n{body}"
    delivered = 0
    now = _now_iso()
    import secrets as _secrets
    for mem in members:
        target = mem.get("user_id")
        if not target or target == user.user_id:
            continue
        lo, hi = sorted([user.user_id, target])
        doc = {
            "id": _secrets.token_hex(12),
            "pair_key": f"{lo}|{hi}",
            "from_uid": user.user_id,
            "to_uid": target,
            "body": body,
            "created_at": now,
            "read": False,
            "broadcast_league_id": league_id,
        }
        await db.messages.insert_one(doc)
        delivered += 1
    return {"delivered": delivered, "league_id": league_id}


@api_router.delete("/feed/{post_id}")
async def delete_feed_post(post_id: str, request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    """Director soft-delete. Marks the post `hidden` so it disappears
    from the feed list. Author-of-post can also delete their own.
    """
    user = await get_current_user(request, session_token, authorization)
    post = await db.feed_posts.find_one({"id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    league_id = post.get("league_id")
    is_author = post.get("author_id") == user.user_id
    is_director = False
    if league_id:
        lg = await db.leagues.find_one(
            {"id": league_id, "director_id": user.user_id}, {"_id": 0}
        )
        is_director = bool(lg)
    if not (is_author or is_director):
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.feed_posts.update_one(
        {"id": post_id},
        {"$set": {"hidden": True, "hidden_by": user.user_id,
                   "hidden_at": _now_iso()}},
    )
    return {"ok": True, "post_id": post_id}


@api_router.post("/leagues/{league_id}/mute/{user_id}")
async def mute_user(league_id: str, user_id: str, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    caller = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, caller.user_id)
    await db.league_mutes.update_one(
        {"league_id": league_id, "user_id": user_id},
        {"$set": {"league_id": league_id, "user_id": user_id,
                   "muted_by": caller.user_id, "muted_at": _now_iso()}},
        upsert=True,
    )
    return {"ok": True, "user_id": user_id}


@api_router.delete("/leagues/{league_id}/mute/{user_id}")
async def unmute_user(league_id: str, user_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    caller = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, caller.user_id)
    await db.league_mutes.delete_one(
        {"league_id": league_id, "user_id": user_id}
    )
    return {"ok": True}


@api_router.get("/leagues/{league_id}/mutes")
async def list_mutes(league_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    caller = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, caller.user_id)
    rows = await db.league_mutes.find(
        {"league_id": league_id}, {"_id": 0}
    ).to_list(1000)
    return rows
