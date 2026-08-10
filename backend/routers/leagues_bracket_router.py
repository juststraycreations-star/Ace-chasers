"""Tournament bracket + team-scramble scoring — Feb 2026 batch.

Endpoints:
  * POST   /api/leagues/{league_id}/bracket/seed
      Director creates a fresh single-elimination bracket from a list
      of member_ids. Byes are auto-inserted so seed count reaches the
      next power of two.
  * GET    /api/leagues/{league_id}/bracket
      Full bracket state: tiers → matches (in order).
  * POST   /api/bracket/matches/{match_id}/report
      Director records a match result. Winner is stamped and slotted
      into the linked next-tier match. Idempotent — replaying the same
      report is a no-op.
  * DELETE /api/leagues/{league_id}/bracket
      Director wipes the current bracket so a new one can be seeded.

Team Scramble:
  * PATCH  /api/cards/{card_id}/scramble-score
      Any cardmate can post one score that gets fanned out to every
      scorecard on the card (single shared write). Reuses the same
      Idempotency-Key contract as `/scorecards/{id}/score`.
"""
from __future__ import annotations

import math
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from fastapi import Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .leagues_router import (
    ProofLog,
    _compute_handicap,
    _require_member,
    api_router,
    db,
    get_current_user,
    ws_manager,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _require_director(league_id: str, user_id: str) -> dict:
    lg = await db.leagues.find_one(
        {"id": league_id, "director_id": user_id}, {"_id": 0}
    )
    if not lg:
        raise HTTPException(status_code=403, detail="Director only")
    return lg


# ══════════════════════════════════════════════════════════════════
# BRACKET
# ══════════════════════════════════════════════════════════════════

class SeedBracketIn(BaseModel):
    member_ids: List[str] = Field(min_length=2)
    season_id: Optional[str] = None


class MatchReportIn(BaseModel):
    winner_id: str  # member_id of the winner
    a_score: Optional[int] = None
    b_score: Optional[int] = None


def _next_pow2(n: int) -> int:
    return 1 if n <= 1 else 2 ** math.ceil(math.log2(n))


def _build_seed_matches(member_ids: List[str]) -> List[Dict[str, Any]]:
    """Standard single-elimination seeding with byes.

    Byes are represented by `None` on the b-side, and the a-side player
    auto-advances. The returned list has (2**k / 2) entries for the
    first tier.
    """
    slots = _next_pow2(len(member_ids))
    # Pad the seed list with None to reach `slots`.
    padded = list(member_ids) + [None] * (slots - len(member_ids))
    matches: List[Dict[str, Any]] = []
    # Pair (0,slots-1), (1,slots-2), ... — classic seed vs bottom.
    for i in range(slots // 2):
        a = padded[i]
        b = padded[slots - 1 - i]
        m = {
            "id": secrets.token_hex(8),
            "tier": 0,
            "a_member_id": a,
            "b_member_id": b,
            "a_score": None,
            "b_score": None,
            "winner_id": a if b is None else (b if a is None else None),
            "advances_to_match_id": None,
            "advances_to_slot": None,  # "a" | "b"
            "completed_at": _now_iso() if (b is None and a is not None) else None,
        }
        matches.append(m)
    return matches


def _build_next_tiers(first_tier: List[dict]) -> List[List[dict]]:
    """Given tier-0, generate the empty match skeleton for every subsequent
    tier and wire up `advances_to_match_id` / `advances_to_slot`.
    """
    tiers: List[List[dict]] = [first_tier]
    current = first_tier
    while len(current) > 1:
        next_tier: List[dict] = []
        for i in range(0, len(current), 2):
            m = {
                "id": secrets.token_hex(8),
                "tier": len(tiers),
                "a_member_id": None,
                "b_member_id": None,
                "a_score": None,
                "b_score": None,
                "winner_id": None,
                "advances_to_match_id": None,
                "advances_to_slot": None,
                "completed_at": None,
            }
            next_tier.append(m)
        # Wire back-pointers from `current` matches into next_tier slots.
        for idx, m in enumerate(current):
            parent = next_tier[idx // 2]
            m["advances_to_match_id"] = parent["id"]
            m["advances_to_slot"] = "a" if idx % 2 == 0 else "b"
        # If a first-tier match was a bye (already has winner), pre-seat
        # them into the next tier's parent.
        if len(tiers) == 1:
            for m in current:
                if m["winner_id"] and m["advances_to_match_id"]:
                    parent = next_tier[[x["id"] for x in next_tier].index(m["advances_to_match_id"])]
                    parent[f"{m['advances_to_slot']}_member_id"] = m["winner_id"]
        tiers.append(next_tier)
        current = next_tier
    return tiers


@api_router.post("/leagues/{league_id}/bracket/seed")
async def seed_bracket(league_id: str, payload: SeedBracketIn, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, user.user_id)
    # Wipe any previous bracket so a fresh seed is deterministic.
    await db.brackets.delete_many({"league_id": league_id})
    first_tier = _build_seed_matches(payload.member_ids)
    tiers = _build_next_tiers(first_tier)
    doc = {
        "id": secrets.token_hex(12),
        "league_id": league_id,
        "season_id": payload.season_id,
        "tiers": tiers,
        "seeded_by": user.user_id,
        "seeded_at": _now_iso(),
    }
    await db.brackets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/leagues/{league_id}/bracket/auto-seed")
async def auto_seed_bracket(league_id: str, request: Request,
                             season_id: Optional[str] = None,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    """Rating-based automatic bracket seeding.

    Fetches all league members, computes each member's rolling handicap,
    and seeds the bracket in ascending handicap order (lowest handicap =
    top-rated = seed #1). Members with no rounds played (handicap 0)
    sort AFTER rated players, at the bottom seeds.
    """
    user = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, user.user_id)
    members = await db.league_members.find(
        {"league_id": league_id}, {"_id": 0}
    ).to_list(500)
    if len(members) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 league members to seed a bracket")
    # Compute handicap per member; unrated (0.0 from no scorecards) is
    # pushed to the bottom of the seed list so rated players fill top seeds.
    ranked: List[Dict[str, Any]] = []
    for m in members:
        h = await _compute_handicap(league_id, m["id"], [3] * 18)
        played = await db.scorecards.count_documents(
            {"league_id": league_id, "member_id": m["id"], "total": {"$gt": 0}}
        )
        ranked.append({
            "id": m["id"],
            "name": m.get("name") or "Player",
            "handicap": h,
            "played": played,
        })
    # Sort: rated players first (played > 0) by handicap asc, then unrated by name.
    ranked.sort(key=lambda r: (0 if r["played"] > 0 else 1, r["handicap"], r["name"].lower()))
    member_ids = [r["id"] for r in ranked]
    await db.brackets.delete_many({"league_id": league_id})
    first_tier = _build_seed_matches(member_ids)
    tiers = _build_next_tiers(first_tier)
    doc = {
        "id": secrets.token_hex(12),
        "league_id": league_id,
        "season_id": season_id,
        "tiers": tiers,
        "seeded_by": user.user_id,
        "seeded_at": _now_iso(),
        "seed_source": "auto_rating",
        "seed_order": [
            {"seed": i + 1, "member_id": r["id"], "name": r["name"],
             "handicap": r["handicap"], "played": r["played"]}
            for i, r in enumerate(ranked)
        ],
    }
    await db.brackets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/leagues/{league_id}/bracket")
async def get_bracket(league_id: str, request: Request,
                       session_token: Optional[str] = Cookie(None),
                       authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_member(league_id, user.user_id)
    doc = await db.brackets.find_one({"league_id": league_id}, {"_id": 0})
    if not doc:
        return None
    return doc


@api_router.post("/bracket/matches/{match_id}/report")
async def report_match(match_id: str, payload: MatchReportIn, request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    # Locate the bracket that contains this match. `tiers` is a list of
    # lists, so dot-notation across two array levels won't work. Scan
    # the (typically small) bracket set instead.
    bracket = None
    match = None
    async for b in db.brackets.find({}, {"_id": 0}):
        for tier in b.get("tiers", []):
            for m in tier:
                if m.get("id") == match_id:
                    bracket = b
                    match = m
                    break
            if match:
                break
        if bracket:
            break
    if not bracket or not match:
        raise HTTPException(status_code=404, detail="Match not found")
    await _require_director(bracket["league_id"], user.user_id)

    tiers = bracket.get("tiers", [])

    if match.get("winner_id") == payload.winner_id and match.get("completed_at"):
        # Idempotent replay.
        return {"already_reported": True, "bracket": bracket}

    if payload.winner_id not in (match.get("a_member_id"), match.get("b_member_id")):
        raise HTTPException(status_code=400, detail="Winner must be one of the match players")

    match["winner_id"] = payload.winner_id
    match["a_score"] = payload.a_score
    match["b_score"] = payload.b_score
    match["completed_at"] = _now_iso()

    # Advance winner to the next tier.
    if match.get("advances_to_match_id"):
        for tier in tiers:
            for m in tier:
                if m["id"] == match["advances_to_match_id"]:
                    slot = match.get("advances_to_slot") or "a"
                    m[f"{slot}_member_id"] = payload.winner_id
                    break

    await db.brackets.update_one(
        {"id": bracket["id"]},
        {"$set": {"tiers": tiers, "updated_at": _now_iso()}},
    )
    winner_mem = await db.league_members.find_one(
        {"id": payload.winner_id}, {"_id": 0, "name": 1}
    )
    winner_name = (winner_mem or {}).get("name") or "Winner"
    tier_idx = match.get("tier", 0)
    total_tiers = len(tiers)
    is_final = tier_idx >= total_tiers - 1
    next_tier_label = "Champion" if is_final else (
        "Final" if tier_idx == total_tiers - 2 else f"Tier {tier_idx + 2}"
    )
    await ws_manager.broadcast(
        f"league:{bracket['league_id']}",
        {"type": "bracket_advance", "match_id": match["id"],
         "winner_id": payload.winner_id, "winner_name": winner_name,
         "tier": tier_idx, "next_tier_label": next_tier_label,
         "is_final": is_final, "manual": True},
    )
    return {"already_reported": False, "bracket": {**bracket, "tiers": tiers}}


@api_router.delete("/leagues/{league_id}/bracket")
async def reset_bracket(league_id: str, request: Request,
                         session_token: Optional[str] = Cookie(None),
                         authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    await _require_director(league_id, user.user_id)
    r = await db.brackets.delete_many({"league_id": league_id})
    return {"deleted": r.deleted_count}


# ══════════════════════════════════════════════════════════════════
# TEAM SCRAMBLE — one shared score per card
# ══════════════════════════════════════════════════════════════════

class ScrambleScoreIn(BaseModel):
    hole: int
    strokes: int


@api_router.patch("/cards/{card_id}/scramble-score")
async def scramble_score(card_id: str, payload: ScrambleScoreIn, request: Request,
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None),
                          idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    """Apply ONE score to every scorecard on the given card. Any cardmate
    can call it. Same server-side idempotency contract as the singleton
    endpoint — a replay of the same key returns the cached response.
    """
    user = await get_current_user(request, session_token, authorization)
    card = await db.cards.find_one({"id": card_id}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Idempotency dedup keyed on (card, user).
    if idempotency_key:
        cached = await db.idempotency_keys.find_one(
            {"key": idempotency_key, "scope": "scramble_score",
             "card_id": card_id, "user_id": user.user_id},
            {"_id": 0, "response": 1},
        )
        if cached and cached.get("response"):
            return cached["response"]

    rd = await db.rounds.find_one({"id": card["round_id"]}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_member(rd["league_id"], user.user_id)

    if payload.hole < 1 or payload.hole > rd["holes"]:
        raise HTTPException(status_code=400, detail="Invalid hole")

    scorecards = await db.scorecards.find(
        {"round_id": card["round_id"], "card_id": card_id},
        {"_id": 0},
    ).to_list(50)
    if not scorecards:
        raise HTTPException(status_code=404, detail="No scorecards on this card")

    idx = payload.hole - 1
    strokes = max(0, int(payload.strokes))
    updated_count = 0
    for sc in scorecards:
        if sc.get("finalized"):
            continue
        old_val = sc["scores"][idx] if idx < len(sc["scores"]) else 0
        new_scores = list(sc["scores"])
        # Pad if the scorecard was created with a shorter hole list.
        while len(new_scores) <= idx:
            new_scores.append(0)
        new_scores[idx] = strokes
        total = sum(new_scores)
        par_total = sum(rd["par_per_hole"][i] for i, s in enumerate(new_scores) if s > 0)
        plus_minus = total - par_total if par_total > 0 else 0
        await db.scorecards.update_one(
            {"id": sc["id"]},
            {"$set": {"scores": new_scores, "total": total,
                       "plus_minus": plus_minus, "updated_at": _now_iso()},
             "$inc": {"version": 1}},
        )
        log = ProofLog(
            scorecard_id=sc["id"], round_id=card["round_id"],
            hole=payload.hole, old_value=old_val, new_value=strokes,
            edited_by_user_id=user.user_id, edited_by_name=user.name,
        )
        await db.proof_logs.insert_one(log.model_dump())
        updated_count += 1

    await ws_manager.broadcast(
        f"round:{card['round_id']}",
        {"type": "score_update", "card_id": card_id, "hole": payload.hole,
         "strokes": strokes, "scramble": True, "edited_by": user.name},
    )
    response = {"ok": True, "updated_count": updated_count,
                "card_id": card_id, "hole": payload.hole, "strokes": strokes}
    if idempotency_key:
        try:
            await db.idempotency_keys.insert_one({
                "key": idempotency_key,
                "scope": "scramble_score",
                "card_id": card_id,
                "user_id": user.user_id,
                "response": response,
                "created_at": _now_iso(),
            })
        except Exception:
            pass
    return response


class ScrambleModeIn(BaseModel):
    scramble_mode: bool


@api_router.patch("/cards/{card_id}/scramble-mode")
async def set_scramble_mode(card_id: str, payload: ScrambleModeIn, request: Request,
                             session_token: Optional[str] = Cookie(None),
                             authorization: Optional[str] = Header(None)):
    """Toggle scramble mode on a card. Director-only."""
    user = await get_current_user(request, session_token, authorization)
    card = await db.cards.find_one({"id": card_id}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    rd = await db.rounds.find_one({"id": card["round_id"]}, {"_id": 0})
    if not rd:
        raise HTTPException(status_code=404, detail="Round not found")
    await _require_director(rd["league_id"], user.user_id)
    await db.cards.update_one(
        {"id": card_id},
        {"$set": {"scramble_mode": bool(payload.scramble_mode)}},
    )
    return {"ok": True, "card_id": card_id, "scramble_mode": bool(payload.scramble_mode)}
