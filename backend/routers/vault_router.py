"""vault_router — Lifetime Scorecard Vault.

Reads directly from the existing `scorecards` + `rounds` collections
(no new storage). Serves the frontend's Vault view with three payloads:

  • recent      — the user's last N scorecards (default 5)
  • by_month    — grouped `{ "2026-02": [scorecards], ... }` for the
                  responsive year/month accordion
  • hole_stats  — per-hole lifetime average (relative to par) across
                  every finalized scorecard the user owns
"""
from __future__ import annotations
from collections import defaultdict
from typing import Optional

from fastapi import Cookie, Header, Request

from .leagues_router import api_router, db, get_current_user


def _plus_minus_row(scores, par):
    """Convert absolute strokes → per-hole delta relative to par.
    Empty holes (0) are treated as unplayed → None so the client can
    render a dash instead of a fake +/- number.
    """
    out = []
    for i, s in enumerate(scores or []):
        p = par[i] if i < len(par) else 3
        out.append(None if not s else (s - p))
    return out


def _round_summary(sc, rd):
    par = (rd or {}).get("par_per_hole") or []
    scores = sc.get("scores") or []
    course_par = sum(par) if par else 0
    total = sc.get("total") or sum(x for x in scores if x)
    return {
        "scorecard_id": sc["id"],
        "round_id": sc.get("round_id"),
        "round_name": (rd or {}).get("name"),
        "course": (rd or {}).get("course_location"),
        "date": (rd or {}).get("date"),
        "holes": len(par),
        "par_per_hole": par,
        "course_par": course_par,
        "scores": scores,
        "scores_vs_par": _plus_minus_row(scores, par),
        "total": total,
        "plus_minus": sc.get("plus_minus", (total - course_par) if course_par else 0),
        "finalized": bool(sc.get("finalized")),
    }


@api_router.get("/vault/summary")
async def vault_summary(request: Request,
                        recent_limit: int = 5,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, session_token, authorization)
    # Find every league_member row this user owns so we can query their
    # scorecards regardless of which league they belong to.
    mem_rows = await db.league_members.find(
        {"user_id": user.user_id}, {"_id": 0, "id": 1}
    ).to_list(500)
    member_ids = [m["id"] for m in mem_rows]
    if not member_ids:
        return {"recent": [], "by_month": {}, "hole_stats": {}, "total_rounds": 0}
    cards = await db.scorecards.find(
        {"member_id": {"$in": member_ids}, "total": {"$gt": 0}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(2000)
    round_ids = list({c.get("round_id") for c in cards if c.get("round_id")})
    rounds = await db.rounds.find(
        {"id": {"$in": round_ids}}, {"_id": 0}
    ).to_list(2000)
    r_by_id = {r["id"]: r for r in rounds}
    summaries = [_round_summary(sc, r_by_id.get(sc.get("round_id"))) for sc in cards]

    # Group by YYYY-MM for the accordion. `date` on the round is the
    # source of truth; fall back to the scorecard `created_at`.
    by_month = defaultdict(list)
    for s in summaries:
        d = (s.get("date") or "")[:7] or "unknown"
        by_month[d].append(s)

    # Per-hole lifetime average (relative to par). Grouped by course +
    # hole number so hole 3 at Course A doesn't average with hole 3 at
    # Course B. Client keys off (course, hole) to fetch the chip.
    hole_stats = defaultdict(lambda: {"sum": 0.0, "n": 0})
    for s in summaries:
        course = s.get("course") or "unknown"
        for i, v in enumerate(s["scores_vs_par"]):
            if v is None:
                continue
            k = f"{course}::{i + 1}"
            hole_stats[k]["sum"] += v
            hole_stats[k]["n"] += 1
    hole_stats_out = {
        k: {"avg": round(v["sum"] / v["n"], 2), "rounds": v["n"]}
        for k, v in hole_stats.items() if v["n"] > 0
    }

    return {
        "recent": summaries[:recent_limit],
        "by_month": dict(by_month),
        "hole_stats": hole_stats_out,
        "total_rounds": len(summaries),
    }
