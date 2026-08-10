"""Round side-data endpoints — chat, CTP entries, director notes,
and (as of Phase 4) the scorecard scoring / proof / finalize / certify
surface previously living inline in `leagues_router.py`.

Attaches all handlers to the same `api_router` instance imported from
`leagues_router`, matching the tail-import pattern used by the other
sub-routers. Router registration order is preserved so URL surface and
auth semantics don't change.
"""
from __future__ import annotations

import random as _random
from typing import Any, Dict, List, Literal, Optional

from fastapi import Cookie, Header, HTTPException, Query, Request
from pydantic import BaseModel

from .leagues_router import (
    AutoPairPayload,
    CTPEntry,
    Card,
    ChatMessage,
    LeagueMember,
    LedgerEntry,
    ProofLog,
    Round,
    Scorecard,
    _compute_handicap,
    _finalize_round,
    _require_member,
    api_router,
    db,
    get_current_user,
    now_iso,
    ws_manager,
)


# ============= CHAT =============
class ChatCreate(BaseModel):
    text: str
    card_id: Optional[str] = None


@api_router.post("/rounds/{round_id}/chat")
async def send_chat(round_id: str, payload: ChatCreate, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    msg = ChatMessage(round_id=round_id, card_id=payload.card_id, user_id=user.user_id,
                       user_name=user.name, text=payload.text)
    await db.chat_messages.insert_one(msg.model_dump())
    await ws_manager.broadcast(f"round:{round_id}", {"type": "chat", "message": msg.model_dump()})
    return msg.model_dump()


@api_router.get("/rounds/{round_id}/chat")
async def get_chat(round_id: str, request: Request,
                    card_id: Optional[str] = Query(None),
                    session_token: Optional[str] = Cookie(None),
                    authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    q = {"round_id": round_id}
    if card_id:
        q["card_id"] = card_id
    msgs = await db.chat_messages.find(q, {"_id": 0}).sort("timestamp", 1).to_list(500)
    return msgs


# ============= DIRECTOR NOTES =============
class DirectorNotesPayload(BaseModel):
    director_notes: str
    ctp_holes: Optional[List[int]] = None


@api_router.patch("/rounds/{round_id}/director-notes")
async def update_director_notes(round_id: str, payload: DirectorNotesPayload, request: Request,
                                  session_token: Optional[str] = Cookie(None),
                                  authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    update = {"director_notes": payload.director_notes}
    if payload.ctp_holes is not None:
        update["ctp_holes"] = payload.ctp_holes
    await db.rounds.update_one({"id": round_id}, {"$set": update})
    await ws_manager.broadcast(f"round:{round_id}", {
        "type": "director_notes", "director_notes": payload.director_notes,
        "ctp_holes": update.get("ctp_holes", rd.get("ctp_holes", [])),
    })
    return {"ok": True}


# ============= CTP ENTRIES =============
class CTPCreate(BaseModel):
    hole: int
    feet: int = 0
    inches: float = 0.0
    member_id: Optional[str] = None  # if omitted, use caller's membership


@api_router.post("/rounds/{round_id}/ctp")
async def create_ctp(round_id: str, payload: CTPCreate, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    caller = await _require_member(rd["league_id"], user.user_id)
    member_id = payload.member_id or caller["id"]
    mem = await db.league_members.find_one({"id": member_id, "league_id": rd["league_id"]}, {"_id": 0})
    if not mem:
        raise HTTPException(status_code=404, detail="Member not found")
    if payload.hole < 1 or payload.hole > rd.get("holes", 18):
        raise HTTPException(status_code=400, detail="Invalid hole")
    if payload.feet < 0 or payload.inches < 0 or payload.inches >= 12:
        raise HTTPException(status_code=400, detail="Invalid distance (inches must be 0..11.99)")
    entry = CTPEntry(round_id=round_id, league_id=rd["league_id"], hole=payload.hole,
                      member_id=member_id, member_name=mem["name"],
                      feet=int(payload.feet), inches=float(payload.inches))
    await db.ctp_entries.insert_one(entry.model_dump())
    await ws_manager.broadcast(f"round:{round_id}", {"type": "ctp_entry", "entry": entry.model_dump()})
    return entry.model_dump()


@api_router.get("/rounds/{round_id}/ctp")
async def list_ctp(round_id: str, request: Request,
                    session_token: Optional[str] = Cookie(None),
                    authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    entries = await db.ctp_entries.find({"round_id": round_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    # Build leaderboard grouped by hole (best = smallest distance)
    by_hole: Dict[int, List[dict]] = {}
    for e in entries:
        e["distance_inches"] = e["feet"] * 12 + e["inches"]
        by_hole.setdefault(e["hole"], []).append(e)
    leaderboard = {}
    for hole, items in by_hole.items():
        items.sort(key=lambda x: x["distance_inches"])
        leaderboard[hole] = items
    return {"entries": entries, "leaderboard": leaderboard, "ctp_holes": rd.get("ctp_holes", [])}


@api_router.delete("/ctp/{entry_id}")
async def delete_ctp(entry_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    e = await db.ctp_entries.find_one({"id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    caller = await _require_member(e["league_id"], user.user_id)
    # Own entries or director
    if caller.get("role") != "director" and caller["id"] != e["member_id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.ctp_entries.delete_one({"id": entry_id})
    await ws_manager.broadcast(f"round:{e['round_id']}", {"type": "ctp_deleted", "entry_id": entry_id})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# PHASE 4 — SCORECARD endpoints (moved from leagues_router.py)
# ══════════════════════════════════════════════════════════════════
class ScoreUpdate(BaseModel):
    hole: int  # 1-indexed
    strokes: int


@api_router.patch("/scorecards/{scorecard_id}/score")
async def update_score(scorecard_id: str, payload: ScoreUpdate, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None),
                        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    user = await get_current_user(request, session_token, authorization)
    if idempotency_key:
        cached = await db.idempotency_keys.find_one(
            {"key": idempotency_key, "scope": "score_update",
             "scorecard_id": scorecard_id, "user_id": user.user_id},
            {"_id": 0, "response": 1},
        )
        if cached and cached.get("response"):
            return cached["response"]
    sc = await db.scorecards.find_one({"id": scorecard_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    await _require_member(sc["league_id"], user.user_id)
    if payload.hole < 1 or payload.hole > len(sc["scores"]):
        raise HTTPException(status_code=400, detail="Invalid hole")

    idx = payload.hole - 1
    old_val = sc["scores"][idx]
    if sc.get("finalized"):
        raise HTTPException(status_code=409, detail="Scorecard already finalized")
    scores = list(sc["scores"])
    scores[idx] = int(payload.strokes)
    total = sum(scores)
    rd = await db.rounds.find_one({"id": sc["round_id"]}, {"_id": 0})
    par_total = sum(rd["par_per_hole"][i] for i, s in enumerate(scores) if s > 0)
    played_strokes = sum(s for s in scores if s > 0)
    plus_minus = played_strokes - par_total if par_total > 0 else 0

    await db.scorecards.update_one(
        {"id": scorecard_id},
        {"$set": {"scores": scores, "total": total, "plus_minus": plus_minus,
                  "updated_at": now_iso()},
         "$inc": {"version": 1}}
    )
    log = ProofLog(scorecard_id=scorecard_id, round_id=sc["round_id"], hole=payload.hole,
                   old_value=old_val, new_value=int(payload.strokes),
                   edited_by_user_id=user.user_id, edited_by_name=user.name)
    await db.proof_logs.insert_one(log.model_dump())
    await ws_manager.broadcast(f"round:{sc['round_id']}", {
        "type": "score_update", "scorecard_id": scorecard_id, "hole": payload.hole,
        "strokes": int(payload.strokes), "total": total, "plus_minus": plus_minus,
        "edited_by": user.name,
    })
    response = {"ok": True, "total": total, "plus_minus": plus_minus}
    if idempotency_key:
        try:
            await db.idempotency_keys.insert_one({
                "key": idempotency_key,
                "scope": "score_update",
                "scorecard_id": scorecard_id,
                "user_id": user.user_id,
                "response": response,
                "created_at": now_iso(),
            })
        except Exception:
            pass
    return response


@api_router.get("/scorecards/{scorecard_id}/proof")
async def get_proof(scorecard_id: str, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    await get_current_user(request, session_token, authorization)
    logs = await db.proof_logs.find({"scorecard_id": scorecard_id}, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return logs


class ScorecardFinalizePayload(BaseModel):
    certified: bool = False


@api_router.post("/scorecards/{scorecard_id}/finalize")
async def finalize_scorecard(scorecard_id: str, payload: ScorecardFinalizePayload,
                             request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    if not payload.certified:
        raise HTTPException(
            status_code=400,
            detail="Certification required. You must attest that the scores are accurate before finalizing.",
        )
    sc = await db.scorecards.find_one({"id": scorecard_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    await _require_member(sc["league_id"], user.user_id)
    if sc.get("finalized"):
        return {"ok": True, "already_finalized": True}
    now = now_iso()
    await db.scorecards.update_one(
        {"id": scorecard_id},
        {"$set": {
            "finalized": True,
            "certified": True,
            "certified_by_user_id": user.user_id,
            "certified_by_name": user.name,
            "certified_at": now,
            "updated_at": now,
        }},
    )
    audit = ProofLog(
        scorecard_id=scorecard_id,
        round_id=sc["round_id"],
        hole=0,
        old_value=0,
        new_value=int(sc.get("total") or 0),
        edited_by_user_id=user.user_id,
        edited_by_name=f"{user.name} · CERTIFIED",
    )
    await db.proof_logs.insert_one(audit.model_dump())
    await ws_manager.broadcast(
        f"round:{sc['round_id']}",
        {"type": "score_update", "scorecard_id": scorecard_id, "finalized": True},
    )
    # Auto-advance the bracket if this is a Match-Play round and the
    # finalize completes a match. Best-effort; the manual director report
    # endpoint remains as an override for ties or disputed calls.
    advance = await _maybe_advance_bracket_on_finalize(sc)
    return {
        "ok": True,
        "finalized": True,
        "certified_by_user_id": user.user_id,
        "certified_at": now,
        "bracket_advance": advance,
    }


async def _maybe_advance_bracket_on_finalize(sc: dict) -> Optional[dict]:
    """When a scorecard on a Match-Play round is finalized, check the
    league's bracket for an open match containing this player. If both
    scorecards on the round are finalized, resolve the winner (lowest
    total wins) and slot them into the linked next-tier match.
    """
    round_id = sc.get("round_id")
    league_id = sc.get("league_id")
    if not round_id or not league_id:
        return None
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0, "format": 1})
    if not lg or lg.get("format") != "Match Play":
        return None
    bracket = await db.brackets.find_one({"league_id": league_id}, {"_id": 0})
    if not bracket:
        return None
    finalizer_mem = sc.get("member_id")
    tiers = bracket.get("tiers", [])
    target = None
    for tier in tiers:
        for m in tier:
            if m.get("winner_id"):
                continue
            if finalizer_mem in (m.get("a_member_id"), m.get("b_member_id")):
                target = m
                break
        if target:
            break
    if not target:
        return None
    a_id = target.get("a_member_id")
    b_id = target.get("b_member_id")
    a_sc = b_sc = None
    if a_id:
        a_sc = await db.scorecards.find_one(
            {"round_id": round_id, "member_id": a_id, "finalized": True},
            {"_id": 0},
        )
    if b_id:
        b_sc = await db.scorecards.find_one(
            {"round_id": round_id, "member_id": b_id, "finalized": True},
            {"_id": 0},
        )
    if not (a_sc and b_sc):
        return {"pending": True, "match_id": target["id"]}
    a_total = a_sc.get("total", 0)
    b_total = b_sc.get("total", 0)
    if a_total == b_total:
        # Broadcast tie so directors/spectators subscribed to the league
        # channel see the pending override state immediately.
        await ws_manager.broadcast(
            f"league:{league_id}",
            {"type": "bracket_tie", "match_id": target["id"],
             "a_member_id": a_id, "b_member_id": b_id,
             "a_total": a_total, "b_total": b_total},
        )
        return {"tied": True, "match_id": target["id"],
                "a_member_id": a_id, "b_member_id": b_id,
                "a_total": a_total, "b_total": b_total}
    winner_id = a_id if a_total < b_total else b_id
    target["winner_id"] = winner_id
    target["a_score"] = a_total
    target["b_score"] = b_total
    target["completed_at"] = now_iso()
    if target.get("advances_to_match_id"):
        for tier in tiers:
            for m in tier:
                if m["id"] == target["advances_to_match_id"]:
                    slot = target.get("advances_to_slot") or "a"
                    m[f"{slot}_member_id"] = winner_id
                    break
    await db.brackets.update_one(
        {"id": bracket["id"]},
        {"$set": {"tiers": tiers, "updated_at": now_iso()}},
    )
    winner_mem = await db.league_members.find_one(
        {"id": winner_id}, {"_id": 0, "name": 1}
    )
    winner_name = (winner_mem or {}).get("name") or "Winner"
    tier_idx = target.get("tier", 0)
    total_tiers = len(tiers)
    is_final = tier_idx >= total_tiers - 1
    next_tier_label = "Champion" if is_final else (
        "Final" if tier_idx == total_tiers - 2 else f"Tier {tier_idx + 2}"
    )
    payload = {
        "type": "bracket_advance",
        "match_id": target["id"],
        "winner_id": winner_id,
        "winner_name": winner_name,
        "tier": tier_idx,
        "next_tier_label": next_tier_label,
        "is_final": is_final,
    }
    await ws_manager.broadcast(f"round:{round_id}", payload)
    await ws_manager.broadcast(f"league:{league_id}", payload)
    return {"resolved": True, "match_id": target["id"],
            "winner_id": winner_id, "winner_name": winner_name,
            "a_total": a_total, "b_total": b_total,
            "tier": tier_idx, "is_final": is_final,
            "next_tier_label": next_tier_label}


@api_router.post("/scorecards/{scorecard_id}/certify")
async def player_self_certify(scorecard_id: str, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    """Player self-certification. Marks the scorecard `player_certified`
    so the director's compliance board can clear it out. Idempotent.
    """
    user = await get_current_user(request, session_token, authorization)
    sc = await db.scorecards.find_one({"id": scorecard_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    m = await _require_member(sc["league_id"], user.user_id)
    if m["id"] != sc["member_id"]:
        raise HTTPException(status_code=403, detail="Only the scorecard owner can self-certify")
    if sc.get("player_certified"):
        return {"ok": True, "already_certified": True}
    now = now_iso()
    await db.scorecards.update_one(
        {"id": scorecard_id},
        {"$set": {"player_certified": True,
                   "player_certified_at": now,
                   "player_certified_by_uid": user.user_id,
                   "updated_at": now}},
    )
    audit = ProofLog(
        scorecard_id=scorecard_id, round_id=sc["round_id"], hole=0,
        old_value=0, new_value=int(sc.get("total") or 0),
        edited_by_user_id=user.user_id,
        edited_by_name=f"{user.name} · PLAYER-CERTIFIED",
    )
    await db.proof_logs.insert_one(audit.model_dump())
    await ws_manager.broadcast(
        f"round:{sc['round_id']}",
        {"type": "score_update", "scorecard_id": scorecard_id, "player_certified": True},
    )
    return {"ok": True, "player_certified": True}


# ══════════════════════════════════════════════════════════════════
# PHASE 4 COMPLETION — ROUND endpoints (Feb 2026)
# Moved from `leagues_router.py`. Same shared `api_router` so the
# URL surface is unchanged. Depends on Card / Scorecard / Round
# models and _compute_handicap / _finalize_round helpers imported
# from the parent module.
# ══════════════════════════════════════════════════════════════════
@api_router.get("/rounds/{round_id}")
async def get_round(round_id: str, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    cards = await db.cards.find({"round_id": round_id}, {"_id": 0}).to_list(100)
    scorecards = await db.scorecards.find({"round_id": round_id}, {"_id": 0}).to_list(500)
    return {"round": rd, "cards": cards, "scorecards": scorecards}


class RoundStatusUpdate(BaseModel):
    status: Literal["scheduled", "active", "completed"]

@api_router.patch("/rounds/{round_id}/status")
async def update_round_status(round_id: str, payload: RoundStatusUpdate, request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    await db.rounds.update_one({"id": round_id}, {"$set": {"status": payload.status}})
    if payload.status == "completed":
        await _finalize_round(round_id)
    return {"ok": True}


class CardCreate(BaseModel):
    label: str
    player_ids: List[str]

@api_router.post("/rounds/{round_id}/cards")
async def create_card(round_id: str, payload: CardCreate, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    card = Card(round_id=round_id, label=payload.label, player_ids=payload.player_ids)
    await db.cards.insert_one(card.model_dump())
    # Create empty scorecards
    for pid in payload.player_ids:
        existing = await db.scorecards.find_one({"round_id": round_id, "member_id": pid})
        if existing:
            await db.scorecards.update_one({"round_id": round_id, "member_id": pid},
                                           {"$set": {"card_id": card.id}})
            continue
        handicap = await _compute_handicap(rd["league_id"], pid, rd["par_per_hole"])
        sc = Scorecard(round_id=round_id, league_id=rd["league_id"], member_id=pid,
                       card_id=card.id, scores=[0]*rd["holes"], handicap_at_round=handicap)
        await db.scorecards.insert_one(sc.model_dump())
    return card.model_dump()


@api_router.post("/rounds/{round_id}/join")
async def join_round(round_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    """Self-serve endpoint that lets any league member sign themselves up
    for an existing round. Creates (or reuses) a solo card labeled with
    the member's name plus their scorecard. This is the counterpart to
    the director-only bulk create_card endpoint above.

    Idempotent — if the user already has a scorecard on the round, the
    existing card + scorecard are returned unchanged.
    """
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)

    # Idempotent short-circuit: already scored on this round.
    existing_sc = await db.scorecards.find_one(
        {"round_id": round_id, "member_id": m["id"]}, {"_id": 0}
    )
    if existing_sc and existing_sc.get("card_id"):
        existing_card = await db.cards.find_one({"id": existing_sc["card_id"]}, {"_id": 0})
        return {
            "already_joined": True,
            "card": existing_card,
            "scorecard": existing_sc,
        }

    # Create a solo card for this player.
    label = f"{m['name'].split(' ')[0]}'s Card"
    card = Card(round_id=round_id, label=label, player_ids=[m["id"]])
    await db.cards.insert_one(card.model_dump())

    # Create their scorecard (or link the existing one to the new card).
    if existing_sc:
        await db.scorecards.update_one(
            {"id": existing_sc["id"]},
            {"$set": {"card_id": card.id}},
        )
        sc = {**existing_sc, "card_id": card.id}
    else:
        handicap = await _compute_handicap(rd["league_id"], m["id"], rd["par_per_hole"])
        sc = Scorecard(
            round_id=round_id, league_id=rd["league_id"], member_id=m["id"],
            card_id=card.id, scores=[0]*rd["holes"], handicap_at_round=handicap,
        )
        await db.scorecards.insert_one(sc.model_dump())
        sc = sc.model_dump()

    await ws_manager.broadcast(
        f"round:{round_id}",
        {"type": "player_joined", "member_id": m["id"], "card_id": card.id},
    )
    return {
        "already_joined": False,
        "card": card.model_dump(),
        "scorecard": sc,
    }


class RoundSweepFinalizePayload(BaseModel):
    # Same certification pattern as the per-scorecard finalize. The
    # director MUST tick the certification checkbox in the sweep modal;
    # the API rejects the payload otherwise. Only unfinalized scorecards
    # for the round are updated; already-certified rows are skipped.
    certified: bool = False
    complete_round: bool = True  # also flip round.status -> completed


@api_router.post("/rounds/{round_id}/finalize")
async def finalize_round_sweep(round_id: str, payload: RoundSweepFinalizePayload,
                                request: Request,
                                session_token: Optional[str] = Cookie(None),
                                authorization: Optional[str] = Header(None)):
    """Sweep-certify every scorecard on the round in one action. Director-only.
    Certification is required. Each affected scorecard gets a ProofLog audit
    entry stamped with the director's user_id and name, and optionally the
    round is marked completed (running the same standings recompute that the
    per-round /status endpoint uses).
    """
    user = await get_current_user(request, session_token, authorization)
    if not payload.certified:
        raise HTTPException(
            status_code=400,
            detail="Certification required. You must attest that the scores are accurate before finalizing.",
        )
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director can sweep-finalize a round")

    now = now_iso()
    open_scs = await db.scorecards.find(
        {"round_id": round_id, "finalized": {"$ne": True}}, {"_id": 0}
    ).to_list(500)
    certified_ids = []
    for sc in open_scs:
        await db.scorecards.update_one(
            {"id": sc["id"]},
            {"$set": {
                "finalized": True,
                "certified": True,
                "certified_by_user_id": user.user_id,
                "certified_by_name": f"{user.name} · DIRECTOR SWEEP",
                "certified_at": now,
                "updated_at": now,
            }},
        )
        audit = ProofLog(
            scorecard_id=sc["id"],
            round_id=round_id,
            hole=0,
            old_value=0,
            new_value=int(sc.get("total") or 0),
            edited_by_user_id=user.user_id,
            edited_by_name=f"{user.name} · DIRECTOR SWEEP-CERTIFIED",
        )
        await db.proof_logs.insert_one(audit.model_dump())
        certified_ids.append(sc["id"])

    round_status = rd.get("status")
    if payload.complete_round and round_status != "completed":
        await db.rounds.update_one({"id": round_id}, {"$set": {"status": "completed"}})
        await _finalize_round(round_id)
        round_status = "completed"

    await ws_manager.broadcast(
        f"round:{round_id}",
        {"type": "score_update", "sweep_finalized": True, "count": len(certified_ids)},
    )
    return {
        "ok": True,
        "certified_scorecard_ids": certified_ids,
        "already_finalized": (await db.scorecards.count_documents({"round_id": round_id})) - len(certified_ids),
        "round_status": round_status,
        "certified_by_user_id": user.user_id,
        "certified_at": now,
    }


# ============= CLUBHOUSE FAIR PLAY AGREEMENT =============
@api_router.post("/rounds/{round_id}/auto-pair")
async def auto_pair(round_id: str, payload: AutoPairPayload, request: Request,
                     session_token: Optional[str] = Cookie(None),
                     authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")

    # Clear existing cards for this round
    await db.cards.delete_many({"round_id": round_id})
    await db.scorecards.delete_many({"round_id": round_id})

    ids = list(payload.member_ids)
    _random.shuffle(ids)
    size = max(1, int(payload.card_size))
    cards_created = []
    for i, chunk_start in enumerate(range(0, len(ids), size)):
        chunk = ids[chunk_start:chunk_start + size]
        label = chr(ord("A") + i)
        card = Card(round_id=round_id, label=f"Card {label}", player_ids=chunk)
        await db.cards.insert_one(card.model_dump())
        for pid in chunk:
            handicap = await _compute_handicap(rd["league_id"], pid, rd["par_per_hole"])
            sc = Scorecard(round_id=round_id, league_id=rd["league_id"], member_id=pid,
                           card_id=card.id, scores=[0]*rd["holes"], handicap_at_round=handicap)
            await db.scorecards.insert_one(sc.model_dump())
        cards_created.append(card.model_dump())

    await ws_manager.broadcast(f"round:{round_id}", {"type": "cards_updated"})
    return {"cards": cards_created}


# ============= CSV EXPORTS =============
# NOTE: `_csv_response` lives in `leagues_router.py`; the CSV endpoints
# that reference it remained there so no local helper is needed here.

@api_router.get("/rounds/{round_id}/payout")
async def get_payout(round_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)
    lg = await db.leagues.find_one({"id": rd["league_id"]}, {"_id": 0})

    # Weekly Payout pool available for this round: entries with round_id=round_id and category=Weekly Payout
    pool_credits = await db.ledger.find({"league_id": rd["league_id"], "round_id": round_id,
                                          "category": "Weekly Payout", "kind": "credit"}, {"_id": 0}).to_list(500)
    pool_debits = await db.ledger.find({"league_id": rd["league_id"], "round_id": round_id,
                                          "category": "Weekly Payout", "kind": "debit"}, {"_id": 0}).to_list(500)
    pool_available = sum(e["amount"] for e in pool_credits) - sum(e["amount"] for e in pool_debits)

    # Scorecards + members
    scs = await db.scorecards.find({"round_id": round_id, "total": {"$gt": 0}}, {"_id": 0}).to_list(500)
    members = await db.league_members.find({"league_id": rd["league_id"]}, {"_id": 0}).to_list(500)
    mmap = {m["id"]: m for m in members}

    # Group by division
    divisions_out = {}
    for s in scs:
        mem = mmap.get(s["member_id"])
        if not mem:
            continue
        div = mem.get("division", "Open")
        divisions_out.setdefault(div, []).append({
            "member_id": s["member_id"],
            "name": mem["name"],
            "picture": mem.get("picture"),
            "total": s["total"],
            "plus_minus": s.get("plus_minus", 0),
            "handicap_at_round": s.get("handicap_at_round", 0),
            "net": s.get("total", 0) - s.get("handicap_at_round", 0),
        })

    # Distribute pool across divisions proportional to # players, then payout curve within each division
    # Curve: 50/30/20 top-3 payouts; if fewer players, only top gets everything.
    payouts = {}
    total_players = sum(len(v) for v in divisions_out.values()) or 1
    for div, players in divisions_out.items():
        players.sort(key=lambda p: (p["net"], p["total"]))
        div_pool = round(pool_available * (len(players) / total_players), 2)
        curve = [0.5, 0.3, 0.2][: min(3, len(players))]
        remaining = 1 - sum(curve)
        if remaining > 0 and curve:
            curve[0] += remaining
        div_payouts = []
        for i, p in enumerate(players):
            share = curve[i] if i < len(curve) else 0
            amount = round(div_pool * share, 2)
            div_payouts.append({
                **p,
                "place": i + 1,
                "payout": amount,
            })
        payouts[div] = {
            "players": div_payouts,
            "pool": div_pool,
        }

    return {
        "round_id": round_id,
        "round_name": rd.get("name"),
        "pool_available": round(pool_available, 2),
        "divisions": payouts,
        "payout_split": lg.get("payout_split", {"pool": 0.7, "ace": 0.2, "club": 0.1}),
    }


# ============= WEEKLY PAYOUT FINALIZE =============
@api_router.post("/rounds/{round_id}/finalize-payout")
async def finalize_payout(round_id: str, request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    """Convert the payout distribution into ledger debit entries against the Weekly Payout pool."""
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    m = await _require_member(rd["league_id"], user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    dist = await get_payout(round_id, request, session_token, authorization)
    entries = []
    for div, block in dist["divisions"].items():
        for p in block["players"]:
            if p["payout"] > 0:
                e = LedgerEntry(league_id=rd["league_id"], kind="debit", category="Weekly Payout",
                                 amount=float(p["payout"]),
                                 note=f"Payout · {p['name']} ({div} · P{p['place']})",
                                 round_id=round_id, member_id=p["member_id"],
                                 created_by=user.user_id)
                await db.ledger.insert_one(e.model_dump())
                entries.append(e.model_dump())
    return {"created": len(entries), "entries": entries}


# The router is included by the main Ace Chasers server.py with the /api
# prefix. CORS is handled globally by the main app. No shutdown handler
# is needed here — the main app owns the Mongo client lifecycle.

