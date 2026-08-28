"""Advanced platform features — Feb 2026 batch:

* GET  /api/rounds/{round_id}/leaderboard        (Item 1 — Singles/Doubles)
* GET  /api/users/me/referral                    (Item 3 — Founder referral)
* POST /api/users/me/redeem-referral             (Item 3 — apply post-signup)

Attaches endpoints to the shared `api_router` from `leagues_router.py`
so the URL surface stays under `/api/*`.

Notes on Doubles/Best-Disc:
  For "Random-Draw Doubles" and "BYOP" the *card* is the team. We take
  the per-hole minimum across every player's scorecard on that card
  (best-disc / scramble semantics) and sum the mins for the team total.
  For "Team" format we sum the players' totals directly.
  For Singles we return one row per player.
"""
from __future__ import annotations

import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from fastapi import Cookie, Header, HTTPException, Request
from pydantic import BaseModel

from .leagues_router import (
    _require_member,
    api_router,
    db,
    get_current_user,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_ref_code() -> str:
    """8-char base32-ish slug. Unique per user, easy to type on paper."""
    # secrets.token_urlsafe(6) yields ~8 chars from a URL-safe alphabet;
    # uppercase for scannability.
    return secrets.token_urlsafe(6).replace("_", "").replace("-", "").upper()[:8]


# ══════════════════════════════════════════════════════════════════
# ITEM 1 — Multi-mode leaderboards
# ══════════════════════════════════════════════════════════════════

def _team_row_for_card(card: dict, scorecards_by_id: Dict[str, dict],
                        members_by_id: Dict[str, dict],
                        par_per_hole: List[int],
                        mode: str) -> Optional[dict]:
    """Aggregate one card into a single leaderboard row.

    mode = "best_disc" → per-hole min across all cardmates' scorecards
    mode = "team_sum"  → straight sum of every cardmate's total
    """
    scs = [sc for sc in scorecards_by_id.values() if sc.get("card_id") == card["id"]]
    if not scs:
        return None
    player_names = []
    for pid in card.get("player_ids", []):
        mem = members_by_id.get(pid)
        if mem:
            player_names.append(mem.get("name") or "Player")

    holes = len(par_per_hole)
    if mode == "best_disc":
        combined = [0] * holes
        for i in range(holes):
            vals = [sc["scores"][i] for sc in scs if i < len(sc.get("scores", [])) and sc["scores"][i] > 0]
            combined[i] = min(vals) if vals else 0
        total = sum(combined)
        played_par = sum(par_per_hole[i] for i, v in enumerate(combined) if v > 0)
        plus_minus = total - played_par if played_par > 0 else 0
        return {
            "team_id": card["id"],
            "team_label": card.get("label") or "Card",
            "player_ids": card.get("player_ids", []),
            "player_names": player_names,
            "combined_scores": combined,
            "total": total,
            "plus_minus": plus_minus,
            "holes_played": sum(1 for v in combined if v > 0),
        }
    # team_sum
    total = sum(sc.get("total", 0) for sc in scs)
    plus_minus = sum(sc.get("plus_minus", 0) for sc in scs)
    return {
        "team_id": card["id"],
        "team_label": card.get("label") or "Card",
        "player_ids": card.get("player_ids", []),
        "player_names": player_names,
        "total": total,
        "plus_minus": plus_minus,
        "holes_played": max((sum(1 for v in sc.get("scores", []) if v > 0) for sc in scs), default=0),
    }


@api_router.get("/rounds/{round_id}/leaderboard")
async def round_leaderboard(round_id: str, request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    """Return a leaderboard shape that matches the round's league format.
    Singles → one row per player; Doubles/BYOP → one row per card using
    best-disc; Team → one row per card summing team totals.
    """
    user = await get_current_user(request, session_token, authorization)
    rd = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    league_id = rd["league_id"]
    await _require_member(league_id, user.user_id)
    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0})
    fmt = (lg or {}).get("format", "Singles")

    scorecards = await db.scorecards.find({"round_id": round_id}, {"_id": 0}).to_list(500)
    cards = await db.cards.find({"round_id": round_id}, {"_id": 0}).to_list(500)
    members = await db.league_members.find({"league_id": league_id}, {"_id": 0}).to_list(500)
    members_by_id = {m["id"]: m for m in members}
    scorecards_by_id = {sc["id"]: sc for sc in scorecards}
    par = rd.get("par_per_hole", [])

    if fmt in ("Random-Draw Doubles", "BYOP"):
        mode = "best_disc"
    elif fmt == "Team":
        mode = "team_sum"
    else:
        mode = "singles"

    if mode == "singles":
        rows = []
        for sc in scorecards:
            m = members_by_id.get(sc.get("member_id"))
            rows.append({
                "member_id": sc.get("member_id"),
                "name": (m or {}).get("name") or "Player",
                "bag_tag": (m or {}).get("bag_tag"),
                "division": (m or {}).get("division") or "Open",
                "total": sc.get("total", 0),
                "plus_minus": sc.get("plus_minus", 0),
                "holes_played": sum(1 for v in sc.get("scores", []) if v > 0),
                "finalized": sc.get("finalized", False),
                "priority_tier": (m or {}).get("priority_tier", False),
            })
        rows.sort(key=lambda r: (r["total"] if r["total"] > 0 else 10**9, -r["holes_played"]))
        return {"format": fmt, "mode": "singles", "rows": rows}

    # Team modes
    rows: List[dict] = []
    for card in cards:
        row = _team_row_for_card(card, scorecards_by_id, members_by_id, par, mode)
        if row:
            rows.append(row)
    rows.sort(key=lambda r: (r["total"] if r["total"] > 0 else 10**9, -r["holes_played"]))
    return {"format": fmt, "mode": mode, "rows": rows}


# ══════════════════════════════════════════════════════════════════
# ITEM 3 — Founder referral
# ══════════════════════════════════════════════════════════════════

class RedeemReferralIn(BaseModel):
    ref_code: str


async def _get_or_mint_ref_code(uid: str) -> str:
    """Return the user's `ref_code`, minting one on first read. Persists
    to `users.ref_code` so the same code stays stable for the account.
    """
    doc = await db.users.find_one({"uid": uid}, {"_id": 0, "ref_code": 1})
    code = (doc or {}).get("ref_code")
    if code:
        return code
    # Collision-safe: retry a few times with a fresh slug.
    for _ in range(6):
        candidate = _new_ref_code()
        clash = await db.users.find_one({"ref_code": candidate}, {"_id": 0, "uid": 1})
        if not clash:
            await db.users.update_one(
                {"uid": uid},
                {"$set": {"ref_code": candidate, "ref_code_created_at": _now_iso()}},
                upsert=True,
            )
            return candidate
    raise HTTPException(status_code=500, detail="Failed to mint referral code")


@api_router.get("/users/me/referral")
async def my_referral(request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    code = await _get_or_mint_ref_code(user.user_id)
    # Count how many people this user has referred.
    referred = await db.users.count_documents({"founder_sponsor_by": user.user_id})
    return {
        "ref_code": code,
        "share_url": f"/signup?ref={code}",
        "referred_count": referred,
    }


@api_router.post("/users/me/redeem-referral")
async def redeem_referral(payload: RedeemReferralIn, request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    """Called by the frontend right after `/api/auth/sync`. Stamps the
    caller with `founder_sponsor_by`, `founder_sponsor_at`, and
    `priority_tier: true` so future league joins put them in the
    priority bag-tag lane.

    Idempotent — a user who's already been stamped can't reassign their
    sponsor by calling this again. This prevents referral-farming.
    """
    user = await get_current_user(request, session_token, authorization)
    code = (payload.ref_code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Missing ref_code")
    me = await db.users.find_one({"uid": user.user_id}, {"_id": 0})
    if not me:
        raise HTTPException(status_code=404, detail="User not found")
    if me.get("founder_sponsor_by"):
        return {"already_redeemed": True, "sponsor_uid": me["founder_sponsor_by"]}
    sponsor = await db.users.find_one({"ref_code": code}, {"_id": 0, "uid": 1, "name": 1})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Unknown referral code")
    if sponsor["uid"] == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot refer yourself")
    now = _now_iso()
    await db.users.update_one(
        {"uid": user.user_id},
        {"$set": {
            "founder_sponsor_by": sponsor["uid"],
            "founder_sponsor_by_name": sponsor.get("name"),
            "founder_sponsor_at": now,
            "priority_tier": True,
        }},
    )
    # Also bump any existing league_member rows to priority so their
    # bag-tag calculations honor the new tier.
    await db.league_members.update_many(
        {"user_id": user.user_id},
        {"$set": {"priority_tier": True}},
    )
    return {
        "already_redeemed": False,
        "sponsor_uid": sponsor["uid"],
        "sponsor_name": sponsor.get("name"),
    }
