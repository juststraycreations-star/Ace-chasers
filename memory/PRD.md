# Ace Chasers — PRD

## Original problem statement
Build and polish "Ace Chasers," a React/FastAPI/MongoDB disc-golf social platform with League Operations, real-time round scoring, compliance, PWA/TWA, and a UDisc-style scorecard grid.

## Current state (Feb 2026)
Full-stack app with Firebase Auth, League Ops, real-time WebSockets, green-themed Scorecard Grid, Compliance board, beta invites via Google Groups, Android PWA/TWA. Production is stable — Cloudflare 520s and WebSocket reconnect loops fixed.

## Implemented in this session
- **P0 — Completed scorecard 1:1 with printed PDF** (`RoundScorecard.jsx`)
  Added a hard early-return branch when `round.status === "completed"`. The completed view renders exclusively: Back nav, "Round Final" pill, Print/PDF button, Round name, and the green `ScorecardGrid`. No toggle, no tabs, no chat FAB, no reconnect footer, no modals, no interactive controls.
- **Offline-first score entry with idempotency** (`/app/frontend/src/lib/offlineQueue.js`)
  New `enqueueScore` API writes to a localStorage queue with a UUID `Idempotency-Key` header per hole write. Coalesces duplicate hole writes. Auto-flushes on `online` events + 15s poll. Score entry is now non-blocking — the UI updates optimistically and never freezes on flaky cellular. Pending badge shown in the live-status footer.
- **Manager welcome / quick-start module** (`/app/frontend/src/components/WelcomeChecklist.jsx`)
  Slate-gray minimalist quick-start block pinned to the top of the League Dashboard for anyone with ≥1 league. Three actions: (1) Generate a Round QR, (2) Configure scoring engine, (3) Post to the clubhouse feed. Tooltips + progress counter.

## Backlog (P1/P2)
- **P1 — Founder Sponsor Referral Flow** — shareable invite link that stamps referred users with a Founder Sponsor badge + priority bag-tag placement.
- **P1 — DM & Moderation** (Item 5 from user's request) — internal DM panel for managers, admin moderation on clubhouse feed (delete post, mute player). Requires new backend router + models.
- **P2 — Pre-finalization simulator** (Item 2) — real-time projected payouts, draft victory graphics, rolling bag-tag reshuffles, schedule calendar publisher.
- **P2 — Rounds extraction Phase 4** — continue splitting `leagues_router.py`.
- **P2 — QR check-in generation** — real QR code render + backend enrollment endpoint (checklist button currently deep-links to league tab).
- **P2 — Backend Idempotency-Key handling** — server currently ignores the header; last-write-wins on `PATCH /scorecards/{id}/score` is already effectively idempotent, but explicit dedup would harden it.

## Architecture (unchanged this session)
- Backend: FastAPI + Motor (Async MongoDB), routers under `/app/backend/routers/`
- Frontend: React (Vite) + Tailwind + Shadcn + Zustand, real-time via WebSockets
- Auth: Firebase Admin (dev-mode fallback for local QA)
- Deploy: Cloudflare tunnel, Android TWA v1.0.3

## Key files touched
- `/app/frontend/src/pages/leagues/RoundScorecard.jsx`
- `/app/frontend/src/pages/leagues/LeagueDashboard.jsx`
- `/app/frontend/src/lib/offlineQueue.js` (new)
- `/app/frontend/src/components/WelcomeChecklist.jsx` (new)
