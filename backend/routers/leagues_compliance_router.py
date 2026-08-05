"""League Compliance dashboard — director-only view showing who has
agreed to the Clubhouse Fair Play terms and, per round, which players
still need to certify their scorecard before finalize can run.

Extracted from `leagues_router.py` as a new domain (there was no
existing endpoint for this — it's the "compliance board" feature). It
attaches to the same `api_router` instance as the other league sub-
routers so the URL surface, prefix, and mount semantics do not change.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request

from .leagues_router import (
    _require_member,
    api_router,
    db,
    get_current_user,
)


@api_router.get("/leagues/{league_id}/compliance")
async def league_compliance_dashboard(league_id: str, request: Request,
                                       session_token: Optional[str] = Cookie(None),
                                       authorization: Optional[str] = Header(None)):
    """Director-only. Returns a one-glance compliance snapshot for the
    league so sweep-finalize never stalls silently.

    Shape:
      {
        "league": {"id", "name", "member_count"},
        "clubhouse_terms": {
          "agreed_count": int,
          "outstanding_count": int,
          "outstanding_members": [ {id, name, bag_tag}, ... ]
        },
        "rounds": [
          {
            "round_id", "name", "date", "status",
            "scorecard_total": int,
            "certified_count": int,
            "finalized_count": int,
            "pending_certification": [
              {"member_id", "member_name", "bag_tag", "scorecard_id",
               "total", "finalized", "certified_by_director"}
            ],
            "can_sweep_finalize": bool  # true when every scorecard is certified
          }, ...
        ]
      }
    """
    user = await get_current_user(request, session_token, authorization)
    m = await _require_member(league_id, user.user_id)
    if m.get("role") != "director":
        raise HTTPException(status_code=403, detail="Only director")

    lg = await db.leagues.find_one({"id": league_id}, {"_id": 0, "id": 1, "name": 1})
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")

    members = await db.league_members.find(
        {"league_id": league_id}, {"_id": 0}
    ).sort("bag_tag", 1).to_list(500)
    members_by_id = {mem["id"]: mem for mem in members}

    # ----- Clubhouse Fair Play agreement rollup -----
    outstanding_members = [
        {"id": mm["id"], "name": mm.get("name"), "bag_tag": mm.get("bag_tag")}
        for mm in members
        if not mm.get("clubhouse_agreed")
    ]
    agreed_count = sum(1 for mm in members if mm.get("clubhouse_agreed"))

    # ----- Per-round scorecard certification -----
    rounds = await db.rounds.find(
        {"league_id": league_id}, {"_id": 0}
    ).sort("date", -1).to_list(200)

    round_summaries = []
    for rd in rounds:
        rid = rd["id"]
        scs = await db.scorecards.find(
            {"round_id": rid}, {"_id": 0}
        ).to_list(500)
        total = len(scs)
        certified = 0
        finalized = 0
        pending = []
        for sc in scs:
            is_finalized = bool(sc.get("finalized"))
            # A scorecard is "certified" for sweep-finalize purposes when
            # either the player themselves accepted certification OR the
            # director already finalised it.
            is_certified = bool(
                sc.get("certified_by_director") or sc.get("player_certified")
                or is_finalized
            )
            if is_finalized:
                finalized += 1
            if is_certified:
                certified += 1
            else:
                mem = members_by_id.get(sc.get("member_id")) or {}
                pending.append({
                    "member_id": sc.get("member_id"),
                    "member_name": mem.get("name") or "Unknown",
                    "bag_tag": mem.get("bag_tag"),
                    "scorecard_id": sc.get("id"),
                    "total": sc.get("total") or 0,
                    "finalized": is_finalized,
                    "certified_by_director": bool(sc.get("certified_by_director")),
                    "player_certified": bool(sc.get("player_certified")),
                })

        round_summaries.append({
            "round_id": rid,
            "name": rd.get("name"),
            "date": rd.get("date"),
            "status": rd.get("status", "scheduled"),
            "scorecard_total": total,
            "certified_count": certified,
            "finalized_count": finalized,
            "pending_certification": pending,
            "can_sweep_finalize": total > 0 and certified == total,
        })

    return {
        "league": {
            "id": lg["id"],
            "name": lg.get("name"),
            "member_count": len(members),
        },
        "clubhouse_terms": {
            "agreed_count": agreed_count,
            "outstanding_count": len(outstanding_members),
            "outstanding_members": outstanding_members,
        },
        "rounds": round_summaries,
    }
