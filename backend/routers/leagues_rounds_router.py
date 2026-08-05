"""Round side-data endpoints — chat, CTP entries, director notes.

Extracted from `leagues_router.py` as phase 3 of the router split. This
covers the "side data" surface of a round: chat threads, closest-to-pin
entries, and the director's per-round notes / CTP hole configuration.

Scoring, finalize, sweep-finalize, WebSocket handlers, and the payout
distribution engine intentionally stay in `leagues_router.py` for now.
Their extraction is a separate, higher-risk task.

Attaches all handlers to the same `api_router` instance imported from
`leagues_router`, matching the tail-import pattern used by clubhouse,
ledger and compliance sub-routers.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import Cookie, Header, HTTPException, Query, Request
from pydantic import BaseModel

from .leagues_router import (
    CTPEntry,
    ChatMessage,
    _require_member,
    api_router,
    db,
    get_current_user,
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
