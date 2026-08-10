# Ace Chasers — PRD

## Original problem statement
Full-stack disc-golf social platform: React/FastAPI/MongoDB with League Ops, real-time round scoring, compliance, PWA/TWA, and UDisc-style scorecard grid.

## Current state (Feb 2026)
Enterprise-grade League Management platform:
- **Formats**: Singles, Random-Draw Doubles, BYOP, Team, **Match Play** (single-elimination bracket)
- Firebase Auth, real-time WebSockets, offline-first score entry (client + server idempotency)
- Manager quick-start, DM, broadcast, feed moderation, pinned schedule announcements
- Real QR self-enroll, pre-finalization simulator with **two share-card templates**
- Founder-Sponsor referral engine, format-aware leaderboards
- **Bracket seeding + reporting** with auto-advance
- **Team scramble** one-shared-score with server-side dedup
- Cloudflare-fronted Android PWA/TWA
- Scorecard/proof/finalize/certify endpoints extracted into `leagues_rounds_router.py` (Phase 4 partial)

## Implemented in this session (Feb 2026)

### Prior passes
- P0 completed-scorecard = printed PDF layout
- Offline-first score entry, welcome checklist
- Server idempotency, QR self-enroll, simulator, DM, moderation
- Multi-mode leaderboards, schedule publisher, founder referral, share cards

### This pass (Items 1, 2, 3, 4)
- **ITEM 1 · Match Play bracket** — new `leagues_bracket_router.py`:
  * `POST /api/leagues/{id}/bracket/seed` — seeds a single-elimination bracket with automatic bye padding to the next power of two
  * `GET /api/leagues/{id}/bracket` — full state (tiers → matches)
  * `POST /api/bracket/matches/{id}/report` — stamps winner, auto-advances into next tier's a/b slot, idempotent replay
  * `DELETE /api/leagues/{id}/bracket` — wipe & reseed
  * League format enum extended with `"Match Play"`; `CreateLeague` shows the option
  * New `BracketView.jsx` renders tier columns with per-match "Wins →" buttons for directors
- **ITEM 2 · Team scramble** — new `scramble_mode: bool` on `Card` model:
  * `PATCH /api/cards/{id}/scramble-score` — fans out ONE score to every scorecard on the card in a single transaction; each cardmate gets a proof-log entry; same `Idempotency-Key` contract as the singleton endpoint
  * `PATCH /api/cards/{id}/scramble-mode` — director-only toggle
- **ITEM 3 · Multi-template share cards** — `renderShareCard({template})` now emits:
  * `"winner"` — Winner's Circle hero layout with trophy, top individual/team, and projected winnings
  * `"leaderboard"` — Season Leaderboard top-5 with rank badges and rows
  * Both include a low-opacity `AC` watermark overlay behind content
  * `LiveSimulatorPanel` shows **Winner card** and **Leaderboard** buttons side-by-side
- **ITEM 4 · Phase-4 router extraction (partial)** — moved the 4 scorecard endpoints out of `leagues_router.py` and into `leagues_rounds_router.py`:
  * `PATCH /api/scorecards/{id}/score`
  * `GET  /api/scorecards/{id}/proof`
  * `POST /api/scorecards/{id}/finalize`
  * `POST /api/scorecards/{id}/certify`
  * Same shared `api_router`, `db`, `ws_manager`, `ProofLog` → URL surface identical, auth semantics unchanged
  * `leagues_router.py` slimmed from ~1731 to ~1467 lines. Regression tests (36+37+38) pass with the moved endpoints.

## Backlog (P1/P2)
- **P2 — Phase 4 completion**: also move `/rounds/{id}/join`, `/rounds/{id}/status`, `/rounds/{id}/cards`, `/rounds/{id}/auto-pair`, `/rounds/{id}/finalize`, `/rounds/{id}/finalize-payout` into `leagues_rounds_router.py`.
- **P2 — Bracket score-driven auto-advance**: on scorecard finalize inside a Match Play round, auto-resolve the linked bracket match (currently the director reports the winner manually).
- **P2 — Multi-division leaderboards**: today the share-card leaderboard is a single division; add division-scoped rendering.
- **P2 — Bracket seed permutations**: manual seed override for tournament directors.

## New collections / new fields
- `brackets` — `{id, league_id, season_id, tiers: [[match, ...], ...], seeded_by, seeded_at}`
- `cards.scramble_mode: bool`
- `idempotency_keys.scope="scramble_score"` (separate namespace)

## New backend endpoints (this pass)
- `POST /api/leagues/{league_id}/bracket/seed`
- `GET  /api/leagues/{league_id}/bracket`
- `POST /api/bracket/matches/{match_id}/report`
- `DELETE /api/leagues/{league_id}/bracket`
- `PATCH /api/cards/{card_id}/scramble-score`
- `PATCH /api/cards/{card_id}/scramble-mode`
- (moved, same URLs) `PATCH /api/scorecards/{id}/score`, `GET /api/scorecards/{id}/proof`, `POST /api/scorecards/{id}/finalize`, `POST /api/scorecards/{id}/certify`

## Key files touched this session
- `/app/backend/routers/leagues_bracket_router.py` (new)
- `/app/backend/routers/leagues_rounds_router.py` (Phase 4 imports + moved endpoints)
- `/app/backend/routers/leagues_router.py` (League format enum + Card.scramble_mode; scorecard endpoints removed)
- `/app/frontend/src/lib/shareCard.js` (rewritten — two templates + watermark)
- `/app/frontend/src/components/LiveSimulatorPanel.jsx` (two share buttons)
- `/app/frontend/src/components/BracketView.jsx` (new)
- `/app/frontend/src/pages/leagues/LeagueDetail.jsx` (Bracket tab)
- `/app/frontend/src/pages/leagues/CreateLeague.jsx` (Match Play option)
- `/app/backend/tests/test_iteration38.py` (new — 5 passing regression tests)

## Testing
- iteration38 → 5/5 pass (bracket seed + report + BYE, scramble fanout with idempotency dedup, scramble-mode director-only, moved scorecard endpoints functional).
- iteration36 (4/4) + iteration37 (6/6) → still green individually.
- Combined pytest run occasionally hits Firebase Identity `TOO_MANY_ATTEMPTS_TRY_LATER` due to burst signups from a single IP — infra artifact, not a code failure.
