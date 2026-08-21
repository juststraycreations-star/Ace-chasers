#!/usr/bin/env python3
"""delete_test_leagues.py — bulk cleanup script for Ace Chasers test leagues.

Wraps the existing production-tested `DELETE /api/leagues/{id}` endpoint so
you get the full 10-collection cascade AND the `deleted_leagues` shadow
snapshot (i.e. every delete is still undo-able for 30 days) exactly as
the in-app "Danger Zone" button does. No direct Mongo access — the
director-role check on the server stays the single source of truth for
who can nuke what.

Cascaded collections (same list the endpoint purges):
    leagues, league_members (bag tags live here as an int field),
    rounds, scorecards, seasons, brackets, ledger, announcements,
    lost_found, stories, feed_posts, and ctp_entries (via round IDs).

Usage
─────
    # Dry-run against preview — never touches the DB
    python delete_test_leagues.py \\
        --token "$FIREBASE_ID_TOKEN" \\
        --ids lg-abc lg-def lg-ghi \\
        --dry-run

    # Actually delete on production
    python delete_test_leagues.py \\
        --token "$FIREBASE_ID_TOKEN" \\
        --ids lg-abc lg-def lg-ghi \\
        --base-url https://acechasers.net \\
        --yes

    # Delete every league whose name starts with "OBS Demo"
    python delete_test_leagues.py \\
        --token "$FIREBASE_ID_TOKEN" \\
        --name-prefix "OBS Demo" \\
        --yes

Grab your Firebase ID token from the browser: DevTools → Application →
Local Storage → `firebase:authUser:<key>` → copy the `stsTokenManager.
accessToken` value. Or set it as `FIREBASE_ID_TOKEN` in your env.

Exit codes
──────────
    0  every requested league deleted (or dry-run reported OK)
    1  at least one delete failed (auth, 403 not-director, 404, 5xx)
    2  bad CLI arguments
"""
from __future__ import annotations
import argparse
import os
import sys
from typing import List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "This script needs `requests`. Install with:\n"
        "    pip install requests\n"
    )
    sys.exit(2)


# ── ANSI colours — degrade gracefully if the terminal doesn't like them ──
def _c(code: str, s: str) -> str:
    if not sys.stdout.isatty():
        return s
    return f"\033[{code}m{s}\033[0m"


def _red(s: str) -> str: return _c("31", s)
def _green(s: str) -> str: return _c("32", s)
def _yellow(s: str) -> str: return _c("33", s)
def _dim(s: str) -> str: return _c("2", s)


# ═══════════════════════════════════════════════════════════════════════
# Core helpers
# ═══════════════════════════════════════════════════════════════════════
def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _fetch_league(base_url: str, token: str, league_id: str) -> Optional[dict]:
    """GET /api/leagues/{id}. Returns None on 404, raises on other errors."""
    r = requests.get(f"{base_url}/api/leagues/{league_id}",
                      headers=_headers(token), timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _resolve_by_name_prefix(base_url: str, token: str, prefix: str) -> List[str]:
    """Ask the server for the caller's leagues and filter locally."""
    r = requests.get(f"{base_url}/api/leagues", headers=_headers(token), timeout=20)
    r.raise_for_status()
    leagues = r.json() or []
    matches = [lg["id"] for lg in leagues
                if (lg.get("name") or "").startswith(prefix)]
    return matches


def _delete_one(base_url: str, token: str, league_id: str,
                 confirm_name: str, dry_run: bool) -> tuple[bool, str]:
    """Return (ok, note)."""
    if dry_run:
        return True, "dry-run · no HTTP call"
    r = requests.delete(
        f"{base_url}/api/leagues/{league_id}",
        headers=_headers(token),
        json={"confirm_name": confirm_name},
        timeout=45,
    )
    if r.status_code == 200:
        body = r.json() or {}
        counts = body.get("per_collection_counts") or {}
        counts_str = ", ".join(f"{k}:{v}" for k, v in counts.items()
                                 if v) or "no child rows"
        return True, f"cascade → {counts_str}"
    # Surface the server's own error message when it's helpful.
    try:
        detail = (r.json() or {}).get("detail") or r.text
    except Exception:
        detail = r.text
    return False, f"HTTP {r.status_code} — {detail}"


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
def main() -> int:
    p = argparse.ArgumentParser(
        description="Bulk-delete Ace Chasers test leagues via the DELETE endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url",
                     default=os.environ.get("ACECHASERS_BASE_URL",
                                            "https://league-manager-hub-3.preview.emergentagent.com"),
                     help="Backend URL (default: env ACECHASERS_BASE_URL or preview).")
    p.add_argument("--token",
                     default=os.environ.get("FIREBASE_ID_TOKEN"),
                     help="Firebase ID token (Bearer). Or set FIREBASE_ID_TOKEN env.")
    p.add_argument("--ids", nargs="+", default=[],
                     help="Explicit league IDs to delete.")
    p.add_argument("--name-prefix",
                     help="Delete every league whose name starts with this string. "
                          "Applied on top of --ids.")
    p.add_argument("--dry-run", action="store_true",
                     help="Resolve names + auth but skip the DELETE call.")
    p.add_argument("--yes", action="store_true",
                     help="Skip the interactive confirmation prompt.")

    args = p.parse_args()

    if not args.token:
        print(_red("✗ Missing --token / FIREBASE_ID_TOKEN — cannot authenticate."),
              file=sys.stderr)
        return 2
    if not args.ids and not args.name_prefix:
        print(_red("✗ Give me --ids or --name-prefix — refusing to nuke everything."),
              file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    print(_dim(f"→ base: {base_url}"))
    print(_dim(f"→ mode: {'DRY-RUN' if args.dry_run else 'LIVE DELETE'}"))

    # ── Resolve target IDs (explicit + prefix search) ──────────────────
    target_ids: List[str] = list(dict.fromkeys(args.ids))  # dedup, preserve order
    if args.name_prefix:
        try:
            found = _resolve_by_name_prefix(base_url, args.token, args.name_prefix)
        except requests.HTTPError as e:
            print(_red(f"✗ Could not list leagues: {e}"), file=sys.stderr)
            return 1
        print(_dim(f"→ name-prefix {args.name_prefix!r} matched {len(found)} league(s)"))
        for lid in found:
            if lid not in target_ids:
                target_ids.append(lid)

    if not target_ids:
        print(_yellow("No leagues resolved from the given filters — nothing to do."))
        return 0

    # ── Fetch each target so we can validate + display the name ────────
    plan: List[tuple[str, str]] = []  # (league_id, league_name)
    print()
    print(_dim("Planned deletions:"))
    for lid in target_ids:
        try:
            lg = _fetch_league(base_url, args.token, lid)
        except requests.HTTPError as e:
            print(f"  {_red('✗')} {lid} — could not fetch ({e})")
            continue
        if lg is None:
            print(f"  {_yellow('!')} {lid} — 404 (already gone or wrong ID)")
            continue
        name = lg.get("name") or "<unnamed>"
        plan.append((lid, name))
        print(f"  {_dim('•')} {lid}  →  {name!r}")

    if not plan:
        print(_yellow("\nNothing to delete after validation."))
        return 0

    # ── Interactive guardrail (skippable with --yes) ───────────────────
    if not args.yes and not args.dry_run:
        print()
        answer = input(_red(f"Delete {len(plan)} league(s) permanently? Type 'yes' to confirm: "))
        if answer.strip().lower() != "yes":
            print(_yellow("Aborted."))
            return 0

    # ── Fire the deletes ───────────────────────────────────────────────
    print()
    print(_dim("Deleting…"))
    ok_ct = fail_ct = 0
    for lid, name in plan:
        ok, note = _delete_one(base_url, args.token, lid,
                                  confirm_name=name, dry_run=args.dry_run)
        if ok:
            ok_ct += 1
            # Requirement: log the deleted league's name on success.
            print(f"  {_green('✓')} deleted {name!r} "
                  f"[{lid}]  {_dim(note)}")
        else:
            fail_ct += 1
            print(f"  {_red('✗')} {name!r} [{lid}]  {note}")

    print()
    print(f"Summary: {_green(f'{ok_ct} ok')} · "
          f"{_red(f'{fail_ct} failed') if fail_ct else _dim('0 failed')}")
    if not args.dry_run and ok_ct:
        print(_dim("Each delete is undo-able for 30 days via "
                    "POST /api/leagues/restore with the audit_id."))
    return 0 if fail_ct == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
