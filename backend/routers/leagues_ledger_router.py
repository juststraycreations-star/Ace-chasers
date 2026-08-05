"""League Ledger endpoints — ledger CRUD, CSV export, and entry-fee
collection with auto-split. Extracted from `leagues_router.py` as phase 2
of the router refactor.

Reuses `api_router`, `db`, `get_current_user`, `_require_member`,
`LedgerEntry`, and `_csv_response` from `leagues_router.py`. Endpoints
attach to the same `api_router` instance so the URL surface, prefix,
and mounting semantics do not change. `server.py` still mounts the
leagues router exactly once.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import Cookie, Header, HTTPException, Query, Request
from pydantic import BaseModel

from .leagues_router import (
    LedgerEntry,
    _csv_response,
    _require_member,
    api_router,
    db,
    get_current_user,
)


# ============= LEDGER CRUD =============
class LedgerCreate(BaseModel):
    kind: Literal["debit", "credit"]
    category: Literal[
        "Ace Pool", "CTP Cash", "Club Payout", "Entry Fee",
        "Weekly Payout", "Club Fund", "Other",
    ]
    amount: float
    note: Optional[str] = ""
    round_id: Optional[str] = None
    member_id: Optional[str] = None


@api_router.post("/leagues/{league_id}/ledger")
async def add_ledger(league_id: str, payload: LedgerCreate, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    entry = LedgerEntry(
        league_id=league_id, kind=payload.kind, category=payload.category,
        amount=float(payload.amount), note=payload.note or "",
        round_id=payload.round_id, member_id=payload.member_id,
        created_by=user.user_id,
    )
    await db.ledger.insert_one(entry.model_dump())
    # Update ace pool total if applicable
    if payload.category == "Ace Pool":
        delta = payload.amount if payload.kind == "credit" else -payload.amount
        await db.leagues.update_one({"id": league_id}, {"$inc": {"ace_pool": delta}})
    return entry.model_dump()


@api_router.get("/leagues/{league_id}/ledger")
async def list_ledger(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    entries = await db.ledger.find({"league_id": league_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    totals = {}
    for e in entries:
        cat = e["category"]
        totals.setdefault(cat, {"credit": 0.0, "debit": 0.0})
        totals[cat][e["kind"]] += e["amount"]
    balance = sum(t["credit"] - t["debit"] for t in totals.values())
    return {"entries": entries, "totals": totals, "balance": balance}


@api_router.get("/leagues/{league_id}/ledger.csv")
async def ledger_csv(league_id: str, request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None),
                      auth: Optional[str] = Query(None)):
    hdr = authorization or (f"Bearer {auth}" if auth else None)
    user = await get_current_user(request, session_token, hdr)
    await _require_member(league_id, user.user_id)
    entries = await db.ledger.find({"league_id": league_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    rows = [["Date", "Kind", "Category", "Amount", "Note"]]
    for e in entries:
        rows.append([e["created_at"], e["kind"], e["category"], e["amount"], e.get("note", "")])
    return _csv_response(rows, f"ledger-{league_id}.csv")


# ============= ENTRY-FEE COLLECT + AUTO-SPLIT =============
class EntryFeePayload(BaseModel):
    round_id: Optional[str] = None
    member_ids: List[str]  # players paying entry
    amount_override: Optional[float] = None  # per-player fee override


@api_router.post("/leagues/{league_id}/entry-fees/collect")
async def collect_entry_fees(league_id: str, payload: EntryFeePayload, request: Request,
                              session_token: Optional[str] = Cookie(None),
                              authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0})
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    per_player = float(payload.amount_override if payload.amount_override is not None else lg.get("entry_fee", 0))
    if per_player <= 0:
        raise HTTPException(status_code=400, detail="Entry fee is 0. Set league.entry_fee or pass amount_override.")

    split = lg.get("payout_split", {"pool": 0.7, "ace": 0.2, "club": 0.1})
    pool_pct = float(split.get("pool", 0.7))
    ace_pct = float(split.get("ace", 0.2))
    club_pct = float(split.get("club", 0.1))

    total = per_player * len(payload.member_ids)
    # 1) Record raw entry-fee credits per member
    for mid in payload.member_ids:
        mem = await db.league_members.find_one({"id": mid, "league_id": league_id}, {"_id": 0})
        note = f"Entry fee · {mem['name']}" if mem else "Entry fee"
        e = LedgerEntry(
            league_id=league_id, kind="credit", category="Entry Fee",
            amount=per_player, note=note, round_id=payload.round_id, member_id=mid,
            created_by=user.user_id,
        )
        await db.ledger.insert_one(e.model_dump())

    # 2) Auto-split debits from escrow into 3 buckets (credit entries so
    #    totals[category] tracks funds available per bucket).
    buckets = [
        ("Weekly Payout", total * pool_pct),
        ("Ace Pool", total * ace_pct),
        ("Club Fund", total * club_pct),
    ]
    for cat, amt in buckets:
        e = LedgerEntry(
            league_id=league_id, kind="credit", category=cat, amount=round(amt, 2),
            note=f"Auto-split from {len(payload.member_ids)} × ${per_player:.2f} entries",
            round_id=payload.round_id, created_by=user.user_id,
        )
        await db.ledger.insert_one(e.model_dump())

    # And a matching debit of the total entry fees so net stays zero
    debit = LedgerEntry(
        league_id=league_id, kind="debit", category="Entry Fee",
        amount=round(total, 2), note="Entry-fee escrow disbursement",
        round_id=payload.round_id, created_by=user.user_id,
    )
    await db.ledger.insert_one(debit.model_dump())

    # Update running ace_pool total
    await db.leagues.update_one(
        {"id": league_id}, {"$inc": {"ace_pool": round(total * ace_pct, 2)}}
    )

    return {
        "collected_from": len(payload.member_ids),
        "total": round(total, 2),
        "split": {
            "weekly_payout": round(total * pool_pct, 2),
            "ace_pool": round(total * ace_pct, 2),
            "club_fund": round(total * club_pct, 2),
        },
    }
