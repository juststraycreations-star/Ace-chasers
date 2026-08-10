# Ace Chasers — PRD

## Original problem statement
Build and polish "Ace Chasers," a React/FastAPI/MongoDB disc-golf social platform with League Operations, real-time round scoring, compliance, PWA/TWA, and a UDisc-style scorecard grid.

## Current state (Feb 2026)
Enterprise-grade League Management platform. Firebase Auth, League Ops, real-time WebSockets, green-themed UDisc-style Scorecard Grid, Compliance board, Cloudflare-fronted Android PWA/TWA. Sign-in and WebSocket reconnect issues resolved. Offline-first score entry with UUID idempotency (client + server). Manager DM + broadcast. Pre-finalization simulator with **live share cards**. Real QR self-enroll. Feed moderation + pinned auto-scheduling. **Format-aware leaderboards (Singles/Doubles/Team/BYOP)**. **Founder-Sponsor referral engine**.

## Implemented in this session (Feb 2026)

### Prior passes
- P0 completed-scorecard = printed PDF layout
- Offline-first score entry (`offlineQueue.js`, localStorage + UUID Idempotency-Key)
- Manager welcome / quick-start module (`WelcomeChecklist.jsx`)
- Server-side idempotency dedup (`Idempotency-Key` header, `idempotency_keys` collection)
- Real QR self-enroll (`RoundQRPanel` + `/rounds/:id/checkin`)
- Pre-finalization simulator (`LiveSimulatorPanel`)
- Manager DM + broadcast + feed moderation (`ManagerDMPanel`, `/feed/:id` DELETE, mute registry)

### This pass (Items 1, 2, 3, 4)
- **ITEM 1 · Multi-mode leaderboards** — new `GET /api/rounds/{id}/leaderboard` returns `mode=singles|best_disc|team_sum` based on the league format. Best-disc semantics = per-hole MIN across cardmates' scorecards; Team = straight sum of totals. Frontend `FormatLeaderboardPanel.jsx` polls every 10s on active rounds and mounts on the RoundScorecard. Regression covers both singles and doubles.
- **ITEM 2 · Schedule publisher & auto-feed sync** — `POST /api/leagues/{id}/rounds` now accepts `course_location` + `publish_announcement` fields and, when opted-in, inserts a **pinned** `FeedPost` with `kind="schedule"` and structured body (date + course + par). Feed list sorts pinned first. `NewRound` modal exposes the fields. `ClubhouseTab` renders a "Pinned" pill on pinned posts.
- **ITEM 3 · Founder-Sponsor referral engine** —
  * Backend: `GET /api/users/me/referral` (lazy-mints an 8-char `ref_code`), `POST /api/users/me/redeem-referral` (stamps `founder_sponsor_by`, `founder_sponsor_at`, `priority_tier: true` and sweeps existing `league_members` rows to inherit `priority_tier`). Self-referral 400, unknown code 404, second redeem idempotent.
  * Frontend: SignUp reads `?ref=CODE` from URL, shows referrer banner, auto-calls redeem after `/auth/sync`. New `ReferralCard.jsx` on Profile (`Copy` + native `Share`). Profile displays a **🏆 Founder Sponsor** pill for `profile.priorityTier`.
- **ITEM 4 · Simulator share cards** — new `renderShareCard()` in `/app/frontend/src/lib/shareCard.js` renders a 1080×1350 canvas with round header, top-3 leaders, 70/20/10 payout tiles, and ace-pool footer. A **Share card** button on the `LiveSimulatorPanel` triggers download + native Web Share when available. Zero external deps (pure HTML5 canvas).

## Backlog (P1/P2)
- **P2 — Bracket / single-elimination match play** — currently: Singles / Random-Draw Doubles / BYOP / Team.
- **P2 — Rounds extraction Phase 4** — continue splitting `leagues_router.py`.
- **P2 — Draft victory graphics** in the simulator (multiple share-card templates).
- **P2 — Team-format score entry UX** — cardmates currently score independently; a "team enter one shared score" mode could speed up scramble events.

## New collections / new fields
- `users.ref_code` (indexed), `users.ref_code_created_at`
- `users.founder_sponsor_by`, `users.founder_sponsor_by_name`, `users.founder_sponsor_at`
- `users.priority_tier: bool`
- `league_members.priority_tier: bool` (propagated by redeem sweep)
- `feed_posts.pinned: bool`, `feed_posts.kind: "post"|"recap"|"schedule"`
- `feed_posts.meta.round_id / meta.round_date / meta.course_location`

## New backend endpoints (this pass)
- `GET /api/rounds/{round_id}/leaderboard`
- `GET /api/users/me/referral`
- `POST /api/users/me/redeem-referral`
- `POST /api/leagues/{id}/rounds` extended with `course_location` and `publish_announcement`

## Architecture
- Backend: FastAPI + Motor (Async MongoDB), routers under `/app/backend/routers/`
- Frontend: React (Vite) + Tailwind + Shadcn + Zustand, real-time via WebSockets
- Auth: Firebase Admin (dev-mode fallback for local QA)
- Deploy: Cloudflare tunnel, Android TWA v1.0.3

## Key files touched this session
- `/app/backend/routers/leagues_advanced_router.py` (new — leaderboard + referral)
- `/app/backend/routers/leagues_router.py` (Round create hook, FeedPost.pinned)
- `/app/backend/routers/leagues_clubhouse_router.py` (pinned-first sort)
- `/app/backend/models.py`, `/app/backend/deps.py` (referral fields on ProfileOut)
- `/app/frontend/src/pages/SignUp.jsx` (`?ref=CODE` capture + redeem)
- `/app/frontend/src/pages/Profile.jsx` (ReferralCard + Founder Sponsor pill)
- `/app/frontend/src/pages/leagues/LeagueDetail.jsx` (course_location + publish toggle)
- `/app/frontend/src/pages/leagues/RoundScorecard.jsx` (FormatLeaderboardPanel mount)
- `/app/frontend/src/components/FormatLeaderboardPanel.jsx` (new)
- `/app/frontend/src/components/ReferralCard.jsx` (new)
- `/app/frontend/src/components/LiveSimulatorPanel.jsx` (Share card button)
- `/app/frontend/src/components/ClubhouseTab.jsx` (Pinned pill + title render)
- `/app/frontend/src/lib/shareCard.js` (new — canvas renderer)
- `/app/backend/tests/test_iteration37.py` (new — 6 passing regression tests)

## Testing
- iteration36 (4/4) + iteration37 (6/6) → **10/10 pass**
