"""push_service.py — server-side FCM fan-out for live round events.

Triggered from mutation endpoints (see `leagues_extensions_router.py`
and `leagues_rounds_router.py`). Reads `push_tokens` for every affected
player and fans out FCM messages with per-token exception isolation so
one stale token can never stall the batch.

Design contract
───────────────
  • `process_live_round_event(round_id, event_type, **ctx)` is the ONE
    public entry point. Event types today:
      - "join_code_rotated"  → silent data payload (no notification body)
      - "payouts_finalized"  → high-priority alert + body
    Adding a new event = one branch in `_build_payload`.

  • Fire-and-forget from the calling route (asyncio.create_task) so a
    slow FCM round-trip never blocks the client waiting for a
    Regenerate/Finalize response.

  • Per-token error isolation via `asyncio.gather(..., return_exceptions=True)`.
    A single 401 / 404 on one dead token cannot stall the rest.

  • Dead-token pruning: FCM returns 404 (`UNREGISTERED`) or 403
    (`SENDER_ID_MISMATCH`) for tokens that will never work again — we
    delete those rows so the next fan-out isn't slowed by them.

  • FCM credentials come from `FIREBASE_SERVICE_ACCOUNT_PATH` in the
    backend env. If that env var is unset (preview, local dev without
    creds), the sender no-ops with a structured log line so the rest of
    the request loop stays healthy. Production must set it.
"""
from __future__ import annotations
import os
import json
import time
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]

FCM_SEND_URL_TEMPLATE = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# One process-wide access-token cache. FCM OAuth tokens live ~1h; we
# refresh lazily on 401 or expiry.
_ACCESS_TOKEN: Dict[str, Any] = {"token": None, "expires_at": 0}


# ══════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════
async def process_live_round_event(round_id: str, event_type: str, **ctx) -> Dict[str, Any]:
    """Fan out FCM messages for a live round mutation.

    Returns a summary `{ sent, failed, pruned, dry_run }` for logging.
    Never raises — caller side-effects are already committed.
    """
    try:
        recipients = await _resolve_recipients(round_id, event_type, ctx)
        if not recipients:
            return {"sent": 0, "failed": 0, "pruned": 0, "dry_run": False}
        payload = _build_payload(round_id, event_type, ctx)
        results = await _fan_out(recipients, payload)
        return results
    except Exception:  # noqa: BLE001 — worker must never bubble
        logger.exception("push_service.process_live_round_event crashed")
        return {"sent": 0, "failed": 0, "pruned": 0, "dry_run": False, "error": True}


# ══════════════════════════════════════════════════════════════════
# Recipient resolution
# ══════════════════════════════════════════════════════════════════
async def _resolve_recipients(round_id: str, event_type: str, ctx: dict) -> List[dict]:
    """Return the token rows that should receive this event.

    join_code_rotated → every checked-in player on the round (scorecards).
    payouts_finalized  → every player in the affected division(s).
    """
    if event_type == "join_code_rotated":
        scs = await db.scorecards.find(
            {"round_id": round_id}, {"_id": 0, "member_id": 1}
        ).to_list(500)
        member_ids = [s["member_id"] for s in scs if s.get("member_id")]
        if not member_ids:
            return []
        members = await db.league_members.find(
            {"id": {"$in": member_ids}}, {"_id": 0, "user_id": 1}
        ).to_list(500)
        user_ids = list({m["user_id"] for m in members if m.get("user_id")})
    elif event_type == "payouts_finalized":
        rd = await db.rounds.find_one({"id": round_id}, {"_id": 0, "league_id": 1})
        if not rd:
            return []
        # Optional narrowing: `division` in ctx narrows to that group.
        member_query: Dict[str, Any] = {"league_id": rd["league_id"]}
        if ctx.get("division"):
            member_query["division"] = ctx["division"]
        members = await db.league_members.find(
            member_query, {"_id": 0, "user_id": 1}
        ).to_list(2000)
        user_ids = list({m["user_id"] for m in members if m.get("user_id")})
    else:
        logger.info("push_service: unknown event_type=%s", event_type)
        return []

    if not user_ids:
        return []
    tokens = await db.push_tokens.find(
        {"user_id": {"$in": user_ids}}, {"_id": 0, "token": 1, "platform": 1, "user_id": 1}
    ).to_list(5000)
    return tokens


# ══════════════════════════════════════════════════════════════════
# Payload composition
# ══════════════════════════════════════════════════════════════════
def _build_payload(round_id: str, event_type: str, ctx: dict) -> Dict[str, Any]:
    """Return a Firebase HTTP v1 `message` body (minus `token`)."""
    if event_type == "join_code_rotated":
        # Silent data payload — no `notification` block → no banner or
        # sound. Just wakes the app so it can re-fetch the fresh code.
        # Android needs `priority: HIGH` for data-only messages to
        # deliver reliably in Doze mode.
        return {
            "data": {
                "type": "join_code_rotated",
                "round_id": round_id,
                "join_code": str(ctx.get("join_code") or ""),
                "old_code": str(ctx.get("old_code") or ""),
            },
            "android": {"priority": "HIGH"},
        }
    if event_type == "payouts_finalized":
        return {
            "notification": {
                "title": "Payouts are live!",
                "body": "Payouts are live! Check the clubhouse ledger to see your cash breakdown.",
            },
            "data": {
                "type": "payouts_finalized",
                "round_id": round_id,
                "league_id": str(ctx.get("league_id") or ""),
                "division": str(ctx.get("division") or ""),
            },
            "android": {
                "priority": "HIGH",
                "notification": {
                    "channel_id": "ace_chasers_payouts",
                    "click_action": "OPEN_CLUBHOUSE_LEDGER",
                },
            },
        }
    return {}


# ══════════════════════════════════════════════════════════════════
# Fan-out with per-token isolation
# ══════════════════════════════════════════════════════════════════
async def _fan_out(recipients: List[dict], payload: Dict[str, Any]) -> Dict[str, int]:
    """Send `payload` to every recipient. One failure never blocks another."""
    creds_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH")
    project_id = os.environ.get("FIREBASE_PROJECT_ID") or "acechaser-38c33"

    if not creds_path or not os.path.exists(creds_path):
        # Dry-run mode — preview/local without creds. Log what would
        # have been sent so an engineer can eyeball the payload.
        logger.info(
            "push_service DRY-RUN · would send to %d device(s): %s",
            len(recipients), json.dumps(payload)[:200],
        )
        return {"sent": 0, "failed": 0, "pruned": 0, "dry_run": True}

    tasks = [
        _send_one(row, payload, creds_path, project_id)
        for row in recipients
    ]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    sent = failed = 0
    prune_tokens: List[str] = []
    for row, outcome in zip(recipients, outcomes):
        if isinstance(outcome, Exception):
            failed += 1
            logger.warning("push_service send failed token=%s err=%s",
                            row["token"][:12] + "…", outcome)
            continue
        if outcome.get("ok"):
            sent += 1
        else:
            failed += 1
            if outcome.get("prune"):
                prune_tokens.append(row["token"])

    if prune_tokens:
        try:
            res = await db.push_tokens.delete_many({"token": {"$in": prune_tokens}})
            pruned_ct = int(res.deleted_count)
        except Exception:  # noqa: BLE001
            logger.exception("push_service prune failed")
            pruned_ct = 0
    else:
        pruned_ct = 0

    return {"sent": sent, "failed": failed, "pruned": pruned_ct, "dry_run": False}


async def _send_one(row: dict, payload: Dict[str, Any], creds_path: str, project_id: str) -> Dict[str, Any]:
    """Send one FCM message. Returns `{ok, prune?, status}`.

    Wrapped so a network error / HTTP non-2xx becomes a return value,
    not an exception, keeping the gather loop clean.
    """
    try:
        access_token = await _get_access_token(creds_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("push_service credential load failed: %s", e)
        return {"ok": False, "status": "creds_error"}

    body = {"message": {"token": row["token"], **payload}}
    url = FCM_SEND_URL_TEMPLATE.format(project_id=project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        return {"ok": False, "status": f"http_error:{e.__class__.__name__}"}

    if resp.status_code == 200:
        return {"ok": True, "status": "sent"}
    # Dead-token statuses — mark for prune.
    if resp.status_code in (404, 410):
        return {"ok": False, "prune": True, "status": "unregistered"}
    detail = ""
    try:
        detail = resp.json().get("error", {}).get("status", "")
    except Exception:  # noqa: BLE001
        pass
    if detail in ("UNREGISTERED", "SENDER_ID_MISMATCH", "INVALID_ARGUMENT"):
        return {"ok": False, "prune": True, "status": detail}
    if resp.status_code == 401:
        # Force a token refresh next call.
        _ACCESS_TOKEN["token"] = None
        _ACCESS_TOKEN["expires_at"] = 0
    return {"ok": False, "status": f"{resp.status_code}:{detail or 'unknown'}"}


# ══════════════════════════════════════════════════════════════════
# OAuth2 access token for FCM HTTP v1
# ══════════════════════════════════════════════════════════════════
async def _get_access_token(creds_path: str) -> str:
    """Return a cached-or-fresh OAuth token for the FCM scope.

    Uses google-auth's service_account.Credentials. Refresh is done in
    a thread pool so the async loop isn't blocked.
    """
    now = time.time()
    if _ACCESS_TOKEN["token"] and _ACCESS_TOKEN["expires_at"] - now > 60:
        return _ACCESS_TOKEN["token"]

    def _refresh():
        # Lazy import — google-auth is a heavy dep, load only when creds
        # are actually configured.
        from google.oauth2 import service_account  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=[FCM_SCOPE],
        )
        creds.refresh(Request())
        return creds.token, int(creds.expiry.timestamp()) if creds.expiry else int(time.time() + 3000)

    token, expires_at = await asyncio.get_running_loop().run_in_executor(None, _refresh)
    _ACCESS_TOKEN["token"] = token
    _ACCESS_TOKEN["expires_at"] = expires_at
    return token
