"""push_digest.py — weekly push-health digest email for league directors.

Aggregates the last N days of `push_notifications_log` rows, groups by
league (via `rounds.league_id`), and emails each league's director a
plain-English summary covering:
  • Successful deliveries (initial + retry both count)
  • Retries succeeded (transient failures that recovered)
  • Permanent drops (tokens that exhausted every retry attempt)
  • Dead tokens pruned (unregistered / sender-mismatch)
  • Broadcast events (join code rotations, payouts, bracket advances)

The digest is triggered by `POST /api/admin/push/digest/run` (admin-gated
by `X-Admin-Key`). A cron / GitHub Action / manual curl is the intended
scheduling surface — no in-process scheduler is introduced so multi-pod
deploys don't accidentally send the digest more than once.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# SMTP config — same env vars beta_router.py uses so operators only
# maintain one set of Gmail credentials.
GMAIL_USER = os.environ.get("GMAIL_SMTP_USER") or ""
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD") or ""
DIGEST_FROM_NAME = "Ace Chasers"


@dataclass
class LeagueDigest:
    """One director-facing digest row. Everything derived from the
    aggregated `push_notifications_log` window for a single league."""
    league_id: str
    league_name: str
    director_uid: str
    director_email: str
    director_name: str
    successes: int = 0
    retries_succeeded: int = 0
    permanent_drops: int = 0
    tokens_pruned: int = 0
    event_count: int = 0
    # For subject-line personalization + template rendering.
    window_days: int = 7
    window_start_iso: str = ""
    window_end_iso: str = ""
    # Truncated token prefixes for the operator (never full tokens).
    failed_token_prefixes: List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# Aggregation
# ══════════════════════════════════════════════════════════════════
async def gather_digests(db, window_days: int = 7,
                          now: Optional[datetime] = None) -> List[LeagueDigest]:
    """Aggregate the push telemetry window into one row per league.

    Only leagues whose director has an email on file and which saw at
    least one push event in the window make the cut — the digest is
    a signal, not spam.
    """
    now = now or datetime.now(timezone.utc)
    window_end = now
    window_start = now - timedelta(days=window_days)

    # Only the fields we actually read — keep the wire cheap.
    projection = {
        "_id": 0, "roundId": 1, "eventType": 1, "phase": 1,
        "totalSent": 1, "totalFailed": 1, "tokensPruned": 1,
        "retriedSent": 1, "permanentlyFailed": 1,
        "failedTokenPrefixes": 1, "timestamp": 1,
    }
    log_rows = await db.push_notifications_log.find(
        {"timestamp": {"$gte": window_start.isoformat(),
                        "$lte": window_end.isoformat()}},
        projection,
    ).to_list(50_000)

    if not log_rows:
        return []

    # Resolve rounds → leagues in one shot.
    round_ids = list({r["roundId"] for r in log_rows if r.get("roundId")})
    round_docs = await db.rounds.find(
        {"id": {"$in": round_ids}}, {"_id": 0, "id": 1, "league_id": 1}
    ).to_list(len(round_ids))
    round_to_league: Dict[str, str] = {
        r["id"]: r["league_id"] for r in round_docs if r.get("league_id")
    }
    league_ids = list(set(round_to_league.values()))
    if not league_ids:
        return []

    league_docs = await db.leagues.find(
        {"id": {"$in": league_ids}},
        {"_id": 0, "id": 1, "name": 1, "director_id": 1},
    ).to_list(len(league_ids))
    director_uids = list({lg.get("director_id") for lg in league_docs
                          if lg.get("director_id")})
    director_docs = await db.users.find(
        {"uid": {"$in": director_uids}},
        {"_id": 0, "uid": 1, "email": 1, "name": 1},
    ).to_list(len(director_uids))
    director_by_uid = {d["uid"]: d for d in director_docs}

    # Roll up per league.
    per_league: Dict[str, LeagueDigest] = {}
    for lg in league_docs:
        director = director_by_uid.get(lg.get("director_id") or "", {})
        email = (director.get("email") or "").strip()
        if not email:
            # Skip leagues whose director hasn't verified an email —
            # digest is a signal, not spam.
            continue
        per_league[lg["id"]] = LeagueDigest(
            league_id=lg["id"],
            league_name=lg.get("name") or "Untitled League",
            director_uid=director.get("uid") or "",
            director_email=email,
            director_name=(director.get("name")
                            or email.split("@", 1)[0]),
            window_days=window_days,
            window_start_iso=window_start.isoformat(),
            window_end_iso=window_end.isoformat(),
        )

    for row in log_rows:
        league_id = round_to_league.get(row.get("roundId") or "")
        if not league_id or league_id not in per_league:
            continue
        digest = per_league[league_id]
        digest.event_count += 1
        digest.tokens_pruned += int(row.get("tokensPruned") or 0)

        if row.get("phase") == "retry":
            digest.retries_succeeded += int(row.get("retriedSent") or 0)
            digest.permanent_drops += int(row.get("permanentlyFailed") or 0)
            for pfx in row.get("failedTokenPrefixes") or []:
                if pfx and pfx not in digest.failed_token_prefixes:
                    digest.failed_token_prefixes.append(pfx)
        else:
            # Initial fan-out row. `totalSent` here = first-pass hits.
            # `totalFailed` may include transients that were retried
            # (recovered) OR terminal drops — those are already
            # covered by the retry follow-up row's fields, so we skip
            # counting them here to avoid double-billing.
            digest.successes += int(row.get("totalSent") or 0)

    # Successes should also include retries that recovered — they DID
    # get delivered, just on a later attempt.
    for d in per_league.values():
        d.successes += d.retries_succeeded

    # Return only leagues with actual activity.
    return [d for d in per_league.values() if d.event_count > 0]


# ══════════════════════════════════════════════════════════════════
# Rendering
# ══════════════════════════════════════════════════════════════════
def _pretty_range(digest: LeagueDigest) -> str:
    """`Feb 9 – Feb 16, 2026` style, using the digest window."""
    try:
        s = datetime.fromisoformat(digest.window_start_iso)
        e = datetime.fromisoformat(digest.window_end_iso)
    except Exception:
        return f"the last {digest.window_days} days"
    same_month = s.month == e.month and s.year == e.year
    if same_month:
        return f"{s.strftime('%b %-d')}–{e.strftime('%-d')}, {e.year}"
    return f"{s.strftime('%b %-d')} – {e.strftime('%b %-d')}, {e.year}"


def render_digest_email(digest: LeagueDigest) -> Tuple[str, str, str]:
    """Return (subject, plain_text, html) for a single league digest."""
    date_range = _pretty_range(digest)
    subject = (f"{digest.league_name} · push-health digest "
                f"({digest.successes} delivered)")

    dropped_line = ""
    if digest.permanent_drops:
        dropped_line = (
            f"\n• {digest.permanent_drops} permanent drop"
            f"{'s' if digest.permanent_drops != 1 else ''}"
            f" (device tokens that exhausted every retry)"
        )
    pruned_line = ""
    if digest.tokens_pruned:
        pruned_line = (
            f"\n• {digest.tokens_pruned} dead token"
            f"{'s' if digest.tokens_pruned != 1 else ''} pruned"
        )
    plain = (
        f"Hey {digest.director_name.split(' ')[0]},\n\n"
        f"Here's the push-notification health digest for "
        f"{digest.league_name} covering {date_range}.\n\n"
        f"• {digest.successes} delivered "
        f"(including {digest.retries_succeeded} recovered after a retry)\n"
        f"• {digest.event_count} broadcast event"
        f"{'s' if digest.event_count != 1 else ''} fanned out"
        f"{dropped_line}{pruned_line}\n\n"
        "You can see the live delivery health any time in the "
        "League Detail → Compliance tab.\n\n"
        "— Ace Chasers"
    )

    dropped_html = (
        f"<li><b>{digest.permanent_drops}</b> permanent drop"
        f"{'s' if digest.permanent_drops != 1 else ''}"
        " — tokens that exhausted every retry attempt</li>"
    ) if digest.permanent_drops else ""
    pruned_html = (
        f"<li><b>{digest.tokens_pruned}</b> dead token"
        f"{'s' if digest.tokens_pruned != 1 else ''} pruned</li>"
    ) if digest.tokens_pruned else ""

    html = f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#f5f5f5;padding:24px;">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:16px;padding:28px 32px;">
  <div style="font-size:11px;font-weight:bold;color:#166534;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;">Push-health digest · {date_range}</div>
  <h1 style="color:#1f4d2e;margin:0 0 16px;font-size:22px;">{digest.league_name}</h1>
  <p style="margin:0 0 16px;color:#334155;">Hey {digest.director_name.split(' ')[0]}, here's how push delivery went this week for your league.</p>
  <ul style="padding-left:18px;line-height:1.7;color:#0f172a;margin:0 0 16px;">
    <li><b style="color:#059669;">{digest.successes}</b> delivered <span style="color:#64748b;">(incl. {digest.retries_succeeded} recovered after a retry)</span></li>
    <li><b>{digest.event_count}</b> broadcast event{'s' if digest.event_count != 1 else ''} fanned out</li>
    {dropped_html}
    {pruned_html}
  </ul>
  <p style="font-size:13px;color:#64748b;margin:20px 0 0;">Live delivery health is always on tap in <b>League Detail → Compliance</b>.</p>
</div></body></html>"""
    return subject, plain, html


# ══════════════════════════════════════════════════════════════════
# SMTP delivery
# ══════════════════════════════════════════════════════════════════
def smtp_send(to_email: str, subject: str, plain: str, html: str) -> Tuple[bool, str]:
    """Send one message via Gmail SMTP. Returns (ok, note).

    Never raises so a broken SMTP for one director can't stall the
    rest of the batch.
    """
    if not GMAIL_USER or not GMAIL_PASSWORD:
        return False, "smtp_not_configured"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{DIGEST_FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
            s.ehlo()
            s.starttls(context=context)
            s.login(GMAIL_USER, GMAIL_PASSWORD)
            s.send_message(msg)
        return True, "sent"
    except Exception as e:  # noqa: BLE001
        logger.exception("push_digest SMTP send failed for %s", to_email)
        return False, f"smtp_error:{type(e).__name__}"


# ══════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════
async def run_weekly_digest(db, window_days: int = 7,
                              dry_run: bool = False,
                              now: Optional[datetime] = None) -> Dict[str, Any]:
    """Aggregate + send. Returns a per-league send summary.

    `dry_run=True` skips the SMTP call so operators can preview subject
    lines / totals from a curl call before turning the flow live.
    """
    digests = await gather_digests(db, window_days=window_days, now=now)
    summary: Dict[str, Any] = {
        "window_days": window_days,
        "dry_run": dry_run,
        "leagues_considered": len(digests),
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "rows": [],
    }
    for d in digests:
        subject, plain, html = render_digest_email(d)
        row: Dict[str, Any] = {
            "league_id": d.league_id,
            "league_name": d.league_name,
            "director_email": d.director_email,
            "subject": subject,
            "successes": d.successes,
            "retries_succeeded": d.retries_succeeded,
            "permanent_drops": d.permanent_drops,
            "tokens_pruned": d.tokens_pruned,
            "event_count": d.event_count,
        }
        if dry_run:
            row["status"] = "dry_run"
            summary["skipped"] += 1
        else:
            ok, note = smtp_send(d.director_email, subject, plain, html)
            row["status"] = note
            if ok:
                summary["sent"] += 1
            else:
                summary["failed"] += 1
        summary["rows"].append(row)
    return summary
