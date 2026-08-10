"""Round side-data endpoints — chat, CTP entries, director notes,
and (as of Phase 4) the scorecard scoring / proof / finalize / certify
surface previously living inline in `leagues_router.py`.

Attaches all handlers to the same `api_router` instance imported from
`leagues_router`, matching the tail-import pattern used by the other
sub-routers. Router registration order is preserved so URL surface and
auth semantics don't change.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import Cookie, Header, HTTPException, Query, Request
from pydantic import BaseModel

from .leagues_router import (
    CTPEntry,
    ChatMessage,
    ProofLog,
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
    return {
        "ok": True,
        "finalized": True,
        "certified_by_user_id": user.user_id,
        "certified_at": now,
    }


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
