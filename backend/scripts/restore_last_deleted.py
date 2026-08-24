#!/usr/bin/env python3
"""restore_last_deleted.py — undo the most recent Delete-League action.

Companion to `delete_test_leagues.py`. If you fat-finger a delete
mid-recording, this reads `GET /api/deleted-leagues`, picks the newest
shadow row you personally created, and restores it via
`POST /api/leagues/restore` — the same endpoint the in-app 30-second
Undo toast uses. No direct Mongo access; the director check + shadow
snapshot integrity stay on the server.

Usage
─────
    # Dry-run — shows which league WOULD be restored, no POST
    python restore_last_deleted.py --token "$FIREBASE_ID_TOKEN" --dry-run

    # Restore the most recent one (default)
    python restore_last_deleted.py --token "$FIREBASE_ID_TOKEN" --yes

    # Restore a specific audit_id (from an earlier delete summary)
    python restore_last_deleted.py --token "$FIREBASE_ID_TOKEN" \\
        --audit-id 5e2a9c3d-... --yes

    # Restore against production
    python restore_last_deleted.py --token "$FIREBASE_ID_TOKEN" \\
        --base-url https://acechasers.net --yes

Grab your Firebase ID token from browser DevTools → Application →
Local Storage → firebase:authUser:<key> → `stsTokenManager.accessToken`.
Or set it as `FIREBASE_ID_TOKEN` in your env.

Exit codes
──────────
    0  restore succeeded (or dry-run printed the plan)
    1  restore failed (auth, 403, no restorable shadow, 5xx)
    2  bad CLI arguments
"""
from __future__ import annotations
import argparse
import os
import sys
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    sys.stderr.write("This script needs `requests`. Install with:\n"
                     "    pip install requests\n")
    sys.exit(2)


# ── ANSI colours — degrade gracefully in non-TTYs ────────────────────
def _c(code, s):
    if not sys.stdout.isatty():
        return s
    return f"\033[{code}m{s}\033[0m"


def _red(s): return _c("31", s)
def _green(s): return _c("32", s)
def _yellow(s): return _c("33", s)
def _dim(s): return _c("2", s)


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _list_deleted(base_url: str, token: str) -> list:
    r = requests.get(f"{base_url}/api/deleted-leagues",
                      headers=_headers(token), timeout=20)
    if r.status_code == 401:
        raise SystemExit(_red("✗ 401 unauthenticated — check your token"))
    if r.status_code == 403:
        raise SystemExit(_red("✗ 403 — you're not a director of any league "
                              "with shadow rows"))
    r.raise_for_status()
    return r.json() or []


def _pick_target(rows: list, audit_id: Optional[str]) -> Optional[dict]:
    """Return the shadow row to restore, or None if nothing matches."""
    if audit_id:
        for r in rows:
            if r.get("id") == audit_id or r.get("audit_id") == audit_id:
                return r
        return None
    # Newest first — API is expected to return sorted by deletedAt desc,
    # but re-sort defensively so a mixed-order backend doesn't burn us.
    restorable = [r for r in rows
                   if r.get("restore_state") != "restored"
                   and r.get("restore_state") != "expired"]
    if not restorable:
        return None
    restorable.sort(key=lambda r: r.get("deletedAt") or r.get("deleted_at") or "",
                     reverse=True)
    return restorable[0]


def _restore(base_url: str, token: str, audit_id: str) -> tuple[bool, str]:
    r = requests.post(f"{base_url}/api/leagues/restore",
                       headers=_headers(token),
                       json={"audit_id": audit_id},
                       timeout=45)
    if r.status_code == 200:
        body = r.json() or {}
        counts = body.get("restored_counts") or body.get("per_collection_counts") or {}
        counts_str = ", ".join(f"{k}:{v}" for k, v in counts.items() if v) or "no child rows"
        return True, f"restored → {counts_str}"
    try:
        detail = (r.json() or {}).get("detail") or r.text
    except Exception:
        detail = r.text
    return False, f"HTTP {r.status_code} — {detail}"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Restore the most recent Delete-League action.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url",
                     default=os.environ.get(
                         "ACECHASERS_BASE_URL",
                         "https://league-manager-hub-3.preview.emergentagent.com"),
                     help="Backend URL (default: env ACECHASERS_BASE_URL or preview).")
    p.add_argument("--token",
                     default=os.environ.get("FIREBASE_ID_TOKEN"),
                     help="Firebase ID token. Or set FIREBASE_ID_TOKEN env.")
    p.add_argument("--audit-id",
                     help="Restore a specific shadow row by its audit_id. "
                          "Default = the newest one you have access to.")
    p.add_argument("--dry-run", action="store_true",
                     help="Print the target row but don't call restore.")
    p.add_argument("--yes", action="store_true",
                     help="Skip the interactive confirmation prompt.")

    args = p.parse_args()

    if not args.token:
        print(_red("✗ Missing --token / FIREBASE_ID_TOKEN — cannot authenticate."),
              file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    print(_dim(f"→ base: {base_url}"))
    print(_dim(f"→ mode: {'DRY-RUN' if args.dry_run else 'LIVE RESTORE'}"))

    try:
        rows = _list_deleted(base_url, args.token)
    except requests.HTTPError as e:
        print(_red(f"✗ Could not list deleted leagues: {e}"), file=sys.stderr)
        return 1

    target = _pick_target(rows, args.audit_id)
    if not target:
        if args.audit_id:
            print(_yellow(f"No shadow row found for audit_id={args.audit_id}"))
        else:
            print(_yellow("No restorable deleted leagues found."))
        return 0

    name = ((target.get("league") or {}).get("name")
             or target.get("league_name") or "<unnamed>")
    when = target.get("deletedAt") or target.get("deleted_at") or "<unknown time>"
    audit_id = target.get("id") or target.get("audit_id")
    counts = target.get("perCollectionCounts") or target.get("per_collection_counts") or {}
    counts_str = ", ".join(f"{k}:{v}" for k, v in counts.items() if v) or "no child rows"

    print()
    print(_dim("Planned restore:"))
    print(f"  {_dim('•')} {name!r}")
    print(f"  {_dim('•')} deleted at   {_dim(when)}")
    print(f"  {_dim('•')} audit_id     {_dim(audit_id)}")
    print(f"  {_dim('•')} snapshot     {_dim(counts_str)}")

    if args.dry_run:
        print(_yellow("\nDry-run complete — no HTTP call issued."))
        return 0

    if not args.yes:
        print()
        answer = input(_green(f"Restore {name!r}? Type 'yes' to confirm: "))
        if answer.strip().lower() != "yes":
            print(_yellow("Aborted."))
            return 0

    print()
    ok, note = _restore(base_url, args.token, audit_id)
    if ok:
        print(f"  {_green('✓')} restored {name!r}  {_dim(note)}")
        return 0
    print(f"  {_red('✗')} {name!r}  {note}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
