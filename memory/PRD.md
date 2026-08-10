# Ace Chasers — PRD

## Original problem statement
Full-stack disc-golf social platform: React/FastAPI/MongoDB with League Ops, real-time round scoring, compliance, PWA/TWA, and UDisc-style scorecard grid.

## Current state (Feb 2026)
Enterprise-grade League Management platform:
- **Formats**: Singles, Random-Draw Doubles, BYOP, Team, Match Play (single-elimination bracket with auto-advance)
- Firebase Auth, real-time WebSockets, offline-first score entry (client + server idempotency)
- Manager quick-start, DM, broadcast, feed moderation, pinned schedule announcements
- Real QR self-enroll, pre-finalization simulator with two share-card templates
- Founder-Sponsor referral engine, format-aware leaderboards
- Bracket seeding with **drag-free reorder + lock + shuffle** override, auto-advance on scorecard finalize
- Team scramble one-shared-score with server-side dedup
- **Phase 4 router split complete** — all `/rounds/*` and `/scorecards/*` endpoints live in `leagues_rounds_router.py`
- Cloudflare-fronted Android PWA/TWA

## Implemented in this session (Feb 2026)

### Prior passes (summary)
- P0 completed-scorecard PDF layout, offline-first, welcome, server idempotency
- QR self-enroll, simulator, DM, moderation, schedule publisher, referral, share cards
- Match Play bracket, team scramble, dual share-card templates, Phase-4 partial (scorecard endpoints)

### This pass (Items 1, 2, 3)
- **ITEM 1 · Auto-advance on scorecard finalize** — new `_maybe_advance_bracket_on_finalize()` runs inside `finalize_scorecard`. Locates the open bracket match containing the finalizer, and when both cardmates on the round are finalized, resolves the winner (lowest total wins) and slots them into the linked next-tier match. Ties → returns `{tied: True}` so the director can call the manual report endpoint. Response now includes `bracket_advance: {pending|resolved|tied}`. Broadcasts a `bracket_advance` WebSocket event.
- **ITEM 2 · Phase-4 completion** — moved 8 endpoints out of `leagues_router.py` into `leagues_rounds_router.py` via a controlled Python-scripted extraction:
  * `GET /api/rounds/{round_id}`
  * `PATCH /api/rounds/{round_id}/status`
  * `POST /api/rounds/{round_id}/cards`
  * `POST /api/rounds/{round_id}/join`
  * `POST /api/rounds/{round_id}/finalize` (director sweep-finalize)
  * `POST /api/rounds/{round_id}/auto-pair`
  * `GET /api/rounds/{round_id}/payout`
  * `POST /api/rounds/{round_id}/finalize-payout`
  * `_csv_response` helper stayed in `leagues_router.py` (only CSV export endpoints consume it there)
  * `leagues_router.py` slimmed from ~1731 → ~1467 lines. `leagues_rounds_router.py` grew to a coherent Round-and-Scorecard surface.
- **ITEM 3 · Seed override UI** — new `SeedManagementPanel.jsx` mounted from `BracketView`. Directors can:
  * Reorder seeds with per-row ↑/↓ buttons (accessible on touch devices; no drag-lib dependency)
  * **Lock** individual seeds so shuffle skips them
  * **Shuffle unlocked** for random draw honoring locked positions
  * Generate the bracket from the exact resulting order
  * Also available on an existing bracket via the "Re-seed" button

## Backlog (P1/P2)
- **P3 — Double-elim grand-final "bracket reset"** — if LB champ wins first GF, play a second decider match. Current MVP: single GF, winner takes all.

## Iteration 42 (Feb 2026) — Confetti, Recap poster, Double elimination

### Item 1 · Champion confetti
- New `/lib/confetti.js` exports `fireChampionConfetti()` — 2.2s cinematic burst (centre pop + side cannons) in the Ace Chasers gold/emerald palette. Wraps `canvas-confetti` (added via yarn).
- `BracketView.jsx` fires it on any `bracket_advance` WebSocket event where `is_final === true`.
- `RoundScorecard.jsx` also fires it when a Match-Play scorecard finalize response resolves the final match, so the finalizer sees the celebration even if they aren't on the bracket tab.

### Item 2 · Round Recap Poster
- New `RoundRecapPoster.jsx` — portrait-letter poster that auto-fires `window.print()`. Contains:
  * **Podium · Top 3**: sorted by NET (total − handicap_at_round), ties → total → holes played
  * **Hot Round**: deepest under-par score of the day (min plus_minus)
  * **Closest to Pin**: one row per CTP hole with winner name + distance
- Data is assembled entirely client-side from `/rounds/{id}/ctp` plus in-memory scorecards — no new backend surface.
- Wired into `RoundScorecard.jsx` as an amber "Recap poster" button next to Print/PDF; visible to the director when at least one scorecard has a score.

### Item 3 · Double Elimination
- New `SeedBracketIn.kind: "single" | "double"` plus a full LB builder `_build_double_elim` in `leagues_bracket_router.py` producing:
  * **Winners' bracket** (unchanged wiring)
  * **Losers' bracket** with 2·(k−1) tiers (`k = log2(next_pow2(n))`). LB matches carry `tier_ref: "lb"`.
  * **Grand Final** node (`tier_ref: "gf"`, `is_grand_final: true`)
- Each WB match now has `loses_to_match_id` + `loses_to_slot` pointing into the correct LB slot. Standard "drop-in" pattern:
  * WB tier 0 loser (index i) → LB tier 0, index i//2, slot a/b
  * WB tier t≥1 loser (index i) → LB tier (2t−1), same index, slot "b"
  * WB Final loser → LB Final slot "b"; WB Final winner → GF slot "a"; LB Final winner → GF slot "b"
- Report / auto-advance flows updated:
  * `POST /api/bracket/matches/{id}/report` now scans WB, LB and GF via `_iter_all_matches`, drops the loser via `loses_to_match_id`, and persists whichever shape the bracket uses.
  * `_maybe_advance_bracket_on_finalize` in `leagues_rounds_router.py` mirrors the same double-elim aware traversal + loser drop, and emits the correct `next_tier_label` ("WB Tier N", "LB Tier N", "Grand Final").
- `POST /api/leagues/{id}/bracket/auto-seed` accepts `?kind=double` and returns the same double-elim shape plus the `seed_order` snapshot for chip UIs.
- **Frontend**
  * `SeedManagementPanel.jsx` — Double-elimination checkbox toggle (auto-disabled below 4 players); passes `kind` in both `seed` and `auto-seed` calls.
  * `BracketView.jsx` — When `bracket.kind === "double"`, renders **three stacked streams**: Winners bracket, Losers bracket (rose title), Grand Final (gold title). Extracted `renderMatch()` and `BracketStream()` helpers for DRY.
  * `BracketPrintOverlay.jsx` — Double-elim now emits three labeled tier groups on the printable poster in the same order.
  * Kind badge visible next to the "Match Play bracket" title when double.
- **MVP limitations** (documented in backlog):
  * Grand Final is a single match. A "bracket reset" second GF match when LB champ wins first is not implemented.
  * Rosters < 4 players silently fall back to single-elim (`kind` field ignored).

## Backend endpoints (this iteration)
- `POST /api/leagues/{league_id}/bracket/seed` now accepts `kind: "single"|"double"` (defaults `single`).
- `POST /api/leagues/{league_id}/bracket/auto-seed?kind=single|double`.
- Extended `POST /api/bracket/matches/{id}/report` — supports loser drop wiring in double-elim.

## Testing
- `tests/test_iteration42.py` — 2/2 pass (double-elim seed shape + WB→LB drop wiring; single-elim regression).
- `tests/test_iteration41.py` — 1/1 pass.
- `tests/test_iteration40.py` — 1/1 pass.
- `tests/test_iteration39.py` — 1/1 pass.
- Total: 5/5 green.

## Iteration 41 (Feb 2026) — Handicap chips, CSV consolidation, Bracket print

### Item 1 · Handicap Preview Chips
- `SeedManagementPanel.jsx` fetches `/api/leagues/{id}/handicaps` on mount and stamps a chip beside each name.
- Rated players → emerald `HCP +2.4` chip. Unrated players (no completed rounds) → slate `HCP —` chip.
- Auto-seed by rating now also folds the response's `seed_order` handicap/played data back into the chip map so re-render is instant and accurate.

### Item 2 · Phase-4 CSV consolidation
- `GET /api/leagues/{league_id}/standings.csv` moved from `leagues_router.py` into `leagues_rounds_router.py`.
- `_csv_response` helper remains in `leagues_router.py` so `leagues_ledger_router.py` (still importing it) is not disturbed. `leagues_rounds_router.py` now imports both `_csv_response` and `_compute_player_rating`.
- URL, response shape, headers and Content-Disposition are byte-identical to the pre-move implementation — no frontend hooks touched.

### Item 3 · Playoff Bracket Print overlay
- New `BracketPrintOverlay.jsx` renders a portrait-letter print canvas (auto-fits tier count via a CSS grid template), winner rows filled emerald, scores in a mono column.
- Embeds an in-page `@media print` block that hides the rest of the app so `window.print()` outputs only the poster. Directors can save as PDF from the same dialog.
- Wired into `BracketView.jsx` as a "Print" button next to Re-seed and Reset. Overlay auto-fires the native print dialog on mount and offers a "Print again" button + "Close".
- `LeagueDetail.jsx` passes `leagueName` down into `BracketView` so the printable header shows the correct league title.

## Backend endpoints (this iteration)
- **Moved** `GET /api/leagues/{league_id}/standings.csv` → `leagues_rounds_router.py` (URL unchanged).

## Testing
- `tests/test_iteration41.py` — 1/1 pass (CSV moved, still 200 + `text/csv` + Handicap header; `/handicaps` shape verified for chip UI).
- `tests/test_iteration40.py` — 1/1 pass (regression: auto-seed + tie-break).
- `tests/test_iteration39.py` — 1/1 pass (regression: auto-advance).

## Iteration 40 (Feb 2026) — Manual Tie-Break, Auto-Seed by Rating, Division Cards, Live Toast

### Item 1 · Manual Match-Play tie-break override
- `_maybe_advance_bracket_on_finalize` now broadcasts a `bracket_tie` WebSocket event on tied match finalizations (both cardmates same total). Auto-advance is blocked; response carries `tied: true` + both member ids + totals.
- New `TieBreakOverridePanel.jsx` — full-screen amber-bordered modal that opens automatically inside `RoundScorecard.jsx` when the finalize response carries `bracket_advance.tied`. Director picks the sudden-death winner and it calls the existing `POST /api/bracket/matches/{id}/report` endpoint.
- The report endpoint now also broadcasts a `league:{league_id}` `bracket_advance` with `manual: true` so viewers see the resolution.

### Item 2 · Rating-based automatic bracket seeding
- New endpoint `POST /api/leagues/{league_id}/bracket/auto-seed` in `leagues_bracket_router.py`.
- Pulls all league members, computes each member's rolling handicap via the existing `_compute_handicap`, sorts ascending (lowest handicap = top-rated = seed #1). Unrated members (no scorecards played) push to the bottom.
- Persisted `seed_source: "auto_rating"` and full `seed_order` array on the bracket doc so the UI can render the pre-seed rationale.
- New "Auto-seed by rating" button wired into `SeedManagementPanel.jsx`. The endpoint response repopulates the visible seed rows so the director can still lock/shuffle before generating.

### Item 3 · Division-specific leaderboard share cards
- `shareCard.js` — `renderLeaderboardTemplate` now accepts a `divisionLabel` and stamps it into the sublabel + a gold pill under the round title.
- New helper `renderDivisionCards({ divisions, roundName, leagueName, acePool })` emits one PNG per division. Filenames are namespaced `ace-chasers-{round}-{division}.png`.
- `LiveSimulatorPanel.jsx` groups standings by member `division` and shows a "Division cards · N" button whenever more than one division is present. Clicking downloads all of them in sequence.

### Item 4 · WebSocket auto-advance live toast
- `_maybe_advance_bracket_on_finalize` and the manual match-report handler now broadcast the `bracket_advance` payload to `league:{league_id}` (in addition to the existing round channel), carrying `winner_name`, `tier`, `next_tier_label`, `is_final`.
- `BracketView.jsx` subscribes to `useWebSocket('/api/ws/leagues/{leagueId}')` when the league format is Match Play and pops a celebratory toast — golden "🏆 Champion" copy on the final match, and "advances to {tier}" on earlier tiers. The bracket state re-fetches so the pin moves live.

## Testing
- `tests/test_iteration40.py` — 1/1 pass (auto-seed by rating, tie detection, manual tie-break resolve + idempotency)
- `tests/test_iteration39.py` — 1/1 pass (regression: auto-advance path still works)

## Backend endpoints (this pass)
- `POST /api/scorecards/{id}/finalize` (extended response with `bracket_advance`)
- (moved, same URLs) 8 `/rounds/*` endpoints now handled by `leagues_rounds_router.py`

## Key files touched this session
- `/app/backend/routers/leagues_router.py` (extracted 8 endpoints; kept `_csv_response`)
- `/app/backend/routers/leagues_rounds_router.py` (accepts extracted endpoints + auto-advance hook)
- `/app/frontend/src/components/SeedManagementPanel.jsx` (new)
- `/app/frontend/src/components/BracketView.jsx` (wires SeedManagementPanel for seed + re-seed)
- `/app/backend/tests/test_iteration39.py` (new — 1 comprehensive E2E test)

## Testing
- iteration39 → 1/1 pass (E2E: Match Play seed → active → both scorecards → auto-advance resolution + winner persisted; Phase-4 endpoints all reachable)
- iteration38 → 5/5 pass alongside iteration39 (6/6 combined)
- iteration36 + iteration37 individually green (Firebase Identity rate limits IP-wide bursts occasionally, unrelated to code)
