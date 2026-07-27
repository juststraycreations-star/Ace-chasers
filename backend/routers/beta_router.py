"""Closed-beta tester signup + admin export.

Public POST endpoint captures name/email/phone from prospective testers,
persists to Mongo, and (best-effort) emails them the Play Console opt-in
link via Gmail SMTP. Admin GET endpoints list + CSV-export the signups
so the app owner can bulk-paste emails into Play Console → Testing →
Closed testing → Testers.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from db import get_db

log = logging.getLogger(__name__)
router = APIRouter()

# Env config (populated from backend/.env)
GMAIL_USER = os.environ.get("GMAIL_SMTP_USER") or ""
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD") or ""
PLAY_OPT_IN_URL = os.environ.get("PLAY_TESTER_OPT_IN_URL") or ""
ADMIN_EMAILS = {
    e.strip().lower()
    for e in (os.environ.get("BETA_ADMIN_EMAILS") or "").split(",")
    if e.strip()
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class BetaSignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    referral_source: Optional[str] = Field(default=None, max_length=200)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send_tester_email(name: str, email: str) -> tuple[bool, str]:
    """Attempts to send the Play tester opt-in email. Returns (ok, note).
    Errors are captured so a broken SMTP does NOT block the signup POST —
    the tester still gets the link on the thank-you screen.
    """
    if not GMAIL_USER or not GMAIL_PASSWORD:
        return False, "SMTP not configured"
    if not PLAY_OPT_IN_URL:
        return False, "Opt-in URL not configured"
    msg = EmailMessage()
    msg["Subject"] = "Ace Chasers · You're on the beta list"
    msg["From"] = f"Ace Chasers <{GMAIL_USER}>"
    msg["To"] = email
    plain = (
        f"Hey {name.split(' ')[0]},\n\n"
        "Thanks for signing up to beta-test Ace Chasers on Android!\n\n"
        "TWO STEPS to install:\n\n"
        "1) Watch for a separate Google Groups invite email — you have to accept it before Google lets you download the beta.\n\n"
        "2) After you accept the Groups invite, tap this link on your Android device (or click on desktop):\n\n"
        f"{PLAY_OPT_IN_URL}\n\n"
        "Then tap 'Become a tester' and 'Download it on Google Play'. Sign in and you're in.\n\n"
        "Heads-up: if you click the install link BEFORE accepting the Groups invite, Google may say the app isn't available in your country — just accept the invite first, then come back.\n\n"
        "Bug reports go to christina.ann.washburn@gmail.com — we read every one.\n\n"
        "See you on the course,\nAce Chasers"
    )
    html = f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#f5f5f5;padding:24px;">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;">
<h1 style="color:#1f4d2e;margin:0 0 12px;">You're on the beta list</h1>
<p>Hey {name.split(' ')[0]},</p>
<p>Thanks for signing up to beta-test <b>Ace Chasers</b> on Android!</p>
<div style="background:#fff8e1;border:1px solid #F5C542;border-radius:12px;padding:16px;margin:20px 0;">
  <div style="font-size:11px;font-weight:bold;color:#8a6d10;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">Two-Step Install</div>
  <p style="margin:0 0 8px;"><b>Step 1:</b> Watch for a separate <b>Google Groups invite</b> email from us and accept it. (Google requires this before allowing the download.)</p>
  <p style="margin:0;"><b>Step 2:</b> Once you accept the Groups invite, click the button below.</p>
</div>
<p style="margin:24px 0;">
  <a href="{PLAY_OPT_IN_URL}" style="display:inline-block;background:#F5C542;color:#000;font-weight:bold;padding:14px 24px;border-radius:10px;text-decoration:none;">
    Install Ace Chasers Beta
  </a>
</p>
<p style="font-size:13px;color:#666;">
  Works on Android <b>and desktop</b>. On desktop the link enrolls you as a tester; on Android it opens Play Store directly.
</p>
<p style="font-size:12px;color:#a94442;background:#fdecea;padding:10px;border-radius:8px;">
  If you click the install link BEFORE accepting the Groups invite, Google may show "app not available in your country" — accept the invite first, then come back.
</p>
<hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
<p style="font-size:12px;color:#999;">
  Bug reports welcome at christina.ann.washburn@gmail.com — we read every one.
</p>
</div></body></html>"""
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
        log.exception("SMTP send failed for %s", email)
        return False, f"smtp_error: {type(e).__name__}"


@router.post("/api/beta-testers/signup")
async def signup(payload: BetaSignupIn):
    """Public — anyone can sign up. Idempotent per email."""
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    db = get_db()
    existing = await db.beta_testers.find_one({"email": email})
    if existing:
        # Idempotent: return the opt-in link but do NOT re-email so we
        # don't spam anyone who submits the form twice.
        return {
            "ok": True,
            "already_signed_up": True,
            "opt_in_url": PLAY_OPT_IN_URL,
            "id": existing.get("id"),
        }
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "email": email,
        "phone": (payload.phone or "").strip() or None,
        "referral_source": (payload.referral_source or "").strip() or None,
        "created_at": _now_iso(),
        "notification_status": "pending",
    }
    ok, note = _send_tester_email(doc["name"], email)
    doc["notification_status"] = "sent" if ok else note
    doc["notified_at"] = _now_iso() if ok else None
    await db.beta_testers.insert_one(doc)
    return {
        "ok": True,
        "already_signed_up": False,
        "opt_in_url": PLAY_OPT_IN_URL,
        "email_sent": ok,
        "id": doc["id"],
    }


async def _require_beta_admin(request: Request, session_token, authorization):
    user = await get_current_user_wrapper(request, session_token, authorization)
    email = (user.get("email") or "").lower()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


async def get_current_user_wrapper(request, session_token, authorization):
    # `deps.get_current_user` returns a Firebase token dict — we just need email
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Auth required")
    from firebase_auth import verify_firebase_token
    token = authorization.split(" ", 1)[1]
    payload = verify_firebase_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@router.get("/api/beta-testers")
async def list_testers(request: Request,
                        session_token: Optional[str] = Cookie(None),
                        authorization: Optional[str] = Header(None)):
    """Admin-only — lists signups newest first."""
    await _require_beta_admin(request, session_token, authorization)
    db = get_db()
    rows = await db.beta_testers.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"count": len(rows), "testers": rows}


@router.get("/api/beta-testers/export.csv")
async def export_csv(request: Request,
                      session_token: Optional[str] = Cookie(None),
                      authorization: Optional[str] = Header(None)):
    """Admin-only — CSV export for pasting into Play Console."""
    await _require_beta_admin(request, session_token, authorization)
    db = get_db()
    rows = await db.beta_testers.find({}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "name", "phone", "referral_source", "signed_up_at", "email_delivered"])
    for r in rows:
        w.writerow([
            r.get("email", ""),
            r.get("name", ""),
            r.get("phone", ""),
            r.get("referral_source", ""),
            r.get("created_at", ""),
            r.get("notification_status", ""),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ace-chasers-beta-testers.csv"'},
    )


@router.delete("/api/beta-testers/{tester_id}")
async def remove_tester(tester_id: str, request: Request,
                          session_token: Optional[str] = Cookie(None),
                          authorization: Optional[str] = Header(None)):
    """Admin-only — remove a tester from the list (e.g. spam)."""
    await _require_beta_admin(request, session_token, authorization)
    db = get_db()
    res = await db.beta_testers.delete_one({"id": tester_id})
    return {"deleted": res.deleted_count}


# ============= EXISTING USERS EXPORT + BLAST =============
@router.get("/api/admin/users/export.csv")
async def export_users_csv(request: Request,
                            session_token: Optional[str] = Cookie(None),
                            authorization: Optional[str] = Header(None)):
    """Admin-only — dumps every registered Ace Chasers user for bulk-paste
    into Play Console → Testing → Closed testing → Testers. Emits `email,
    name, uid, signed_up_at` for every user doc with a non-empty email.
    """
    await _require_beta_admin(request, session_token, authorization)
    db = get_db()
    rows = await db.users.find(
        {"email": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "email": 1, "name": 1, "uid": 1, "displayName": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "name", "uid", "signed_up_at"])
    for r in rows:
        w.writerow([
            r.get("email", ""),
            r.get("name") or r.get("displayName", ""),
            r.get("uid", ""),
            r.get("created_at", ""),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ace-chasers-users.csv"'},
    )


@router.post("/api/admin/users/beta-invite-all")
async def invite_all_users_to_beta(request: Request,
                                     session_token: Optional[str] = Cookie(None),
                                     authorization: Optional[str] = Header(None)):
    """Admin-only — send the Play Console opt-in email to EVERY registered
    user with a valid email. Idempotent: users who already have an entry
    in beta_testers are skipped. Rate-limited implicitly by Gmail SMTP
    (Gmail free tier allows ~500 recipients/day)."""
    await _require_beta_admin(request, session_token, authorization)
    db = get_db()
    rows = await db.users.find(
        {"email": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "email": 1, "name": 1, "displayName": 1, "uid": 1},
    ).to_list(5000)
    sent = 0
    failed = 0
    skipped = 0
    now = _now_iso()
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if not EMAIL_RE.match(email):
            skipped += 1
            continue
        # Skip if already emailed via beta_testers signup
        existing = await db.beta_testers.find_one({"email": email})
        if existing and existing.get("notification_status") == "sent":
            skipped += 1
            continue
        name = r.get("name") or r.get("displayName") or "player"
        ok, note = _send_tester_email(name, email)
        # Upsert into beta_testers so we don't spam on the next blast
        await db.beta_testers.update_one(
            {"email": email},
            {"$set": {
                "email": email,
                "name": name,
                "referral_source": "admin_bulk_invite",
                "notification_status": "sent" if ok else note,
                "notified_at": now if ok else None,
                "updated_at": now,
            }, "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "created_at": now,
            }},
            upsert=True,
        )
        if ok:
            sent += 1
        else:
            failed += 1
    return {"ok": True, "total_users": len(rows), "sent": sent, "failed": failed, "skipped_already_invited": skipped}
