# Ace Chasers — PRD

## Original problem statement
Build and polish "Ace Chasers," a React/FastAPI/MongoDB disc-golf social platform with League Operations, real-time round scoring, compliance, PWA/TWA, and a UDisc-style scorecard grid.

## Current state (Feb 2026)
Enterprise-grade League Management platform. Firebase Auth, League Ops, real-time WebSockets, green-themed Scorecard Grid, Compliance board, Cloudflare-fronted Android PWA/TWA. Sign-in and WebSocket reconnect issues resolved. Offline-first score entry with UUID idempotency. Manager DM + broadcast. Pre-finalization simulator. Real QR self-enroll. Feed moderation.

## Implemented in this session (Feb 2026)

### Prior pass
- **P0 — Completed scorecard 1:1 with printed PDF** (`RoundScorecard.jsx` early-return branch)
- **Offline-first score entry with idempotency** (`/app/frontend/src/lib/offlineQueue.js`) — localStorage queue + `Idempotency-Key` header
- **Manager welcome / quick-start module** (`WelcomeChecklist.jsx`) — pinned to League Dashboard

### This pass (Items 2, 3, 4, 5 extensions)
- **ITEM 4 · Server-side idempotency** — `PATCH /api/scorecards/{id}/score` now reads `Idempotency-Key` header, caches response in `idempotency_keys` collection, and replays return the original result byte-for-byte with zero duplicate `proof_logs` and no double increment of `scorecards.version`. Verified by `test_iteration36::test_score_idempotency_key_dedupes`.
- **ITEM 3 · Real QR self-enroll**
  * Backend: `POST /api/rounds/{id}/self-enroll` (auto-joins league if needed, creates or reuses card+scorecard, idempotent). `GET /api/rounds/{id}/qr` returns the deep-link payload.
  * Frontend: `RoundQRPanel.jsx` renders a scannable `QRCodeCanvas` (via `qrcode.react`) per round on the director's League Detail page. New public route `/rounds/:roundId/checkin` handled by `RoundCheckin.jsx`.
- **ITEM 2 · Pre-finalization simulator** — `LiveSimulatorPanel.jsx` mounted at the top of the `RoundScorecard` for directors while `round.status === "active"`. Read-only projections of (a) 70/20/10 payout split from the ledger's round-fee entries, (b) bag-tag reshuffle with old→new deltas.
- **ITEM 5 · Manager DM + Feed moderation**
  * Backend: `POST /api/leagues/{id}/broadcast` (director-only, fans out to every member's DM tray via existing `messages` collection). `DELETE /api/feed/{post_id}` (author or director soft-hides). `POST/DELETE /api/leagues/{id}/mute/{uid}` + `GET /api/leagues/{id}/mutes` (director mute registry).
  * Frontend: `ManagerDMPanel.jsx` mounted above the tabs on League Detail for directors — Broadcast + DM modal. `ClubhouseTab.jsx` renders per-post moderation icons (delete + mute) for directors and post authors. Feed list filters `hidden` posts.

## Backlog (P1/P2)
- **P1 — Founder Sponsor Referral Flow** — shareable invite link that stamps referred users with a Founder Sponsor badge + priority bag-tag placement.
- **P2 — Schedule Calendar publisher** (last remaining Item 2 sub-feature) — auto-publish scheduled round dates as structured feed announcements.
- **P2 — Draft victory graphics** in the simulator (share-card preview).
- **P2 — Rounds extraction Phase 4** — continue splitting `leagues_router.py`.
- **P2 — Bracket match play format** — currently we support Singles, Doubles (Best-disc), Random-Draw Doubles, BYOP, Team.

## Architecture
- Backend: FastAPI + Motor (Async MongoDB), routers under `/app/backend/routers/`
- Frontend: React (Vite) + Tailwind + Shadcn + Zustand, real-time via WebSockets
- Auth: Firebase Admin (dev-mode fallback for local QA)
- Deploy: Cloudflare tunnel, Android TWA v1.0.3

## New collections & indexes
- `idempotency_keys` — `{key, scope, scorecard_id, user_id, response, created_at}` — dedup replays on score writes.
- `league_mutes` — `{league_id, user_id, muted_by, muted_at}` — director mute registry.
- `messages` (existing) — broadcast rows tagged with `broadcast_league_id` for audit.
- `feed_posts` (existing) — soft-deletion via `hidden`, `hidden_by`, `hidden_at`.

## Key files touched this session
- `/app/backend/routers/leagues_router.py` (score endpoint idempotency)
- `/app/backend/routers/leagues_extensions_router.py` (new — QR/broadcast/moderation)
- `/app/backend/routers/leagues_clubhouse_router.py` (feed list filters hidden)
- `/app/frontend/src/pages/leagues/RoundScorecard.jsx` (early-return + simulator mount)
- `/app/frontend/src/pages/leagues/LeagueDetail.jsx` (DM panel + per-round QR)
- `/app/frontend/src/pages/leagues/LeagueDashboard.jsx` (welcome checklist)
- `/app/frontend/src/pages/RoundCheckin.jsx` (new)
- `/app/frontend/src/components/RoundQRPanel.jsx` (new)
- `/app/frontend/src/components/LiveSimulatorPanel.jsx` (new)
- `/app/frontend/src/components/ManagerDMPanel.jsx` (new)
- `/app/frontend/src/components/WelcomeChecklist.jsx` (new, prior pass)
- `/app/frontend/src/components/ClubhouseTab.jsx` (moderation controls)
- `/app/frontend/src/lib/offlineQueue.js` (new, prior pass)
- `/app/frontend/src/App.jsx` (new checkin route)
- `/app/backend/tests/test_iteration36.py` (new — 4 passing regression tests)
