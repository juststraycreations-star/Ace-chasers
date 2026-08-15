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

## Iteration 43 (Feb 2026) — Auto cache-bust on deploy

### Item · Build version stamp + auto-reload prompt
- **Backend**: `GET /api/version` returns `{ build_id, built_at }`. `build_id` defaults to the backend boot timestamp; if `ACE_BUILD_ID` is set in the environment (e.g. git SHA from the deploy pipeline) it takes precedence. Contract is stable across calls to the same process.
- **Vite**: `__ACE_BUILD_ID__` is baked in at build time via `define`. Sources: `ACE_BUILD_ID` env var (Vercel/Netlify/Docker), falls back to `'dev'` for `vite dev` (which short-circuits the check).
- **Frontend watcher** (`/lib/buildVersion.js` → `startBuildVersionWatcher`): mounted once in `App.jsx`. Runs a first check 20s after boot, polls every 5 min, and on `window.focus` / `online`. When `build_id !== __ACE_BUILD_ID__` it opens a persistent Sonner toast — "New version available · Reload" — with a Reload action that:
  1. Unregisters every service worker for the origin
  2. Clears every Cache Storage entry
  3. Hard-reloads with `?v=<timestamp>` cache-buster
- **Login page**: mirrored the inline `<CacheNotice />` "Sign-in trouble?" banner onto `Login.jsx` (was previously Signup-only) so users landing directly on `/login` see the same manual escape hatch.

### Testing
- `tests/test_iteration43.py` — 2/2 pass (endpoint shape + stability across calls).
- Full suite `39-43` — **9/9 PASS**.
- Frontend smoke: login page renders, zero console errors, cache-notice banner visible.

## Backend endpoints (this iteration)
- `GET /api/version` — build id + boot timestamp.

## Deployment note
- CI/CD should set `ACE_BUILD_ID=<git-sha>` **before both** `vite build` (frontend) **and** the backend container start, so client bundle and server report the same id. Any subsequent deploy with a different id will trigger the reload prompt for every open tab within 5 minutes.

## Iteration 51 (Feb 2026) — Feed post `media[]` array (composer no longer drops extras)

- **Backend**: `FeedPost` model + `FeedPostCreate` payload extended with `media: List[{kind: "image"|"video", path, poster?}]`. `POST /api/leagues/{id}/feed` now:
  1. Accepts the new `media[]` array as the canonical form.
  2. Folds any legacy `image_path`/`video_path`/`video_poster` payload into `media[]` at write time so pre-iteration-51 clients keep working.
  3. Mirrors the first-of-kind media back onto the legacy single-item fields on the persisted doc so pre-iteration-51 renderers (mobile clients, share cards) still show media.
- **Frontend composer adapter** (`ClubhouseTab.jsx`): uploads every queued file in order and posts a single feed entry with the full `media[]`. Oversize toasts (Image >8MB, Video >25MB) fire per-item, before any upload.
- **Feed post render**: iterates `p.media[]` when present; falls back to `image_path` / `video_path` for legacy posts. Every attachment gets its own `feed-post-image-<id>-<i>` / `feed-post-video-<id>-<i>` testid.
- **Testing**: `tests/test_iteration51.py` — 3/3 PASS (full round-trip with 2 images + 1 video; legacy image_path acceptance + normalization; empty body + empty media rejected 400). Full regression suite still green.

## Iteration 50 (Feb 2026) — ClubhouseFeedComposer swap + global Toaster mount

### Item 1 · ClubhouseFeedComposer
- New `/app/frontend/src/components/ClubhouseFeedComposer.jsx` — polished standalone composer surface using `lucide-react` icons, slate-50 section header, emerald primary CTA, and a horizontal multi-attachment thumbnail strip. Emits `onPostSubmit({ text, media })` where `media` is `Array<{ file, id, preview, isVideo }>`.
- `ClubhouseTab.jsx` swap: old inline composer JSX + state (postImage/postVideo/etc) removed. New `submitPost({ text, media })` adapter maps the composer payload to the current backend contract — uploads first-of-kind image and first-of-kind video from the queued files (extra items dropped; captured in a code comment as a future backend-array enhancement).
- Data-testids preserved for existing e2e tests: `new-post`, `post-input`, `post-image-btn`, `post-video-btn`, `post-submit`, `post-media-preview`. Per-thumb clear became `post-media-clear-<id>`.

### Item 2 · Global `<Toaster />` mount (long-standing silent-toast bug fixed)
- `App.jsx` now imports `Toaster` from `@/components/ui/sonner` and mounts `<Toaster richColors position="top-right" />` once inside `<LeagueAuthProvider>`.
- **Root cause** flagged by testing_agent iteration_43: the sonner Toaster wrapper existed under `components/ui/sonner.jsx` but was never rendered anywhere in the app tree. Every `toast.success`/`toast.error` call across the entire app (post delete, mute, story upload, announcement, LF post, resolve, oversize guards) has been silent since bootstrap. Now they all render.

### Testing
- `test_iteration43.json` — 8/9 assertions on the composer PASS; the 1 flag (missing Toaster) is fixed here.
- `test_iteration44.json` — targeted retest **4/4 PASS**, `retest_needed: false`, zero UI bugs.

## Backlog (P3 nice-to-haves from iteration 43 code review)
- `URL.revokeObjectURL` cleanup on successful submit + composer unmount to prevent blob URL leaks.
- Prefer `crypto.randomUUID()` over deprecated `String.prototype.substr` in the composer's id generator.
- Extend `/api/leagues/{id}/feed` to accept media arrays (multiple images/videos per post) so the composer no longer silently drops extras.

## Iteration 49 (Feb 2026) — Winner chip · Palette sweep · RoundCard extract · Bulk-print watermark

### Item 1 · Winner name stamped on completed rounds
- `_finalize_round` in `leagues_router.py` now writes `winner_id` + `winner_name` back to the round document (hot-round finisher). `GET /api/leagues/{id}/rounds` echoes both fields.
- Backfill note (P3): pre-existing completed rounds still show "Winner · —" until they are re-finalized. One-off migration recommended.

### Item 2 · Standings + Ledger palette sweep
- `StandingsTab.jsx` — white-card container (`rounded-2xl border border-slate-200 bg-white shadow-sm`), emerald first-rank number, emerald division chip, slate export button, slate text tokens throughout.
- `LedgerTab.jsx` — same token migration via bulk replace: `card-surface` → white card, `text-zinc-*` → `text-slate-*`, `[#F5C542]` → `text-emerald-700`, `chip-orange`/`chip-green` → emerald pills. Verified no dark-zinc surfaces remain.
- BracketView already matched the palette — no changes needed.

### Item 3 · `<RoundCard variant="active|upcoming|completed" />` extracted
- New `/app/frontend/src/components/RoundCard.jsx` — three-variant pure component with shared `primaryBtn` / `secondaryBtn` class tokens. LeagueDetail Rounds tab now delegates rendering to RoundCard, dropping ~150 lines of duplicated JSX.
- Completed variant surfaces the new `data-testid="round-winner-chip-<id>"` — emerald pill for populated winner, slate pill for legacy rounds.

### Item 4 · Bulk print watermark
- `BulkScorecardPrintOverlay.jsx` now renders an `ac-bulk-print-header` block per card group containing an inline emerald SVG disc + ACE CHASERS wordmark + round name + "Sheet N of M · <card label>". On-screen the header sits at opacity-70; `@media print` promotes it to full opacity so paper copies look tournament-official.

## Testing
- Backend pytest — **17/17 PASS** across iterations 39-49. New test: `test_iteration49.py::test_completed_round_carries_winner_name_and_id`.
- Frontend testing_agent (`/app/test_reports/iteration_42.json`) — **15/15 assertions PASS**. Zero UI/integration/design issues, `retest_needed: false`.

## Backlog (P3 nice-to-haves surfaced by iteration 42 code review)
- Bulk print header opacity-50 on-screen (already opacity-1 in print). Cosmetic.
- One-off migration to backfill `winner_name`/`winner_id` on historic completed rounds so the archive is uniformly populated.
- Audit `ledger-grid` CSS class in `App.css`/`index.css` for any residual `text-zinc-*` declarations.
- Extend pytest to seed a ledger row so emerald chip variants (chip-orange/green migration) can be visually asserted end-to-end.

## Iteration 48 (Feb 2026) — Clubhouse feed as default landing + multimedia parity

- **Default landing tab**: `LeagueDetail.jsx` `initialTab` default flipped from `"rounds"` to `"clubhouse"`. `?tab=<key>` URL param still overrides — `?tab=rounds` lands on Rounds as before.
- **Composer multimedia (1:1 with main Feed)**: `ClubhouseTab.jsx` composer now supports text-only, image-only (max 8MB, `image/*`), video-only (max 25MB, `video/*`), or text+media combos. Two testids surface each upload: `post-image-btn` + `post-video-btn`. Media items are mutually exclusive per post — selecting one clears the other. Live preview renders inside `post-media-preview` with `post-media-clear` (X button) to remove.
- **Backend model + endpoint**: `FeedPost` model in `leagues_router.py` gained `image_path`, `video_path`, `video_poster` fields. `POST /api/leagues/{id}/feed` (in `leagues_clubhouse_router.py`) accepts the new payload and validates that body-or-media is present (400 otherwise). Uploads flow through the existing `/api/files/upload` (Cloudinary-backed).
- **Feed rendering**: each post now emits `feed-post-image-{id}` and/or `feed-post-video-{id}` when media is attached. Images open in the existing `Lightbox`; videos render an HTML5 `<video controls>` element with the optional `video_poster` frame.
- **Moderation shortcuts preserved**: director sees `feed-delete-btn-{postId}` on every post and `feed-mute-btn-{postId}` on posts by other members (untouched by this pass, verified in the test report).
- **Testing** (`/app/test_reports/iteration_41.json`): 10/10 pytest on the new `POST /api/leagues/{id}/feed` contract, 13/13 Playwright specs on default landing, tab override, composer with image + video, media mutual exclusion, media rendering in feed, and moderation gates. Zero issues found.

## Backlog (P3 nice-to-haves surfaced by iteration 41 code review)
- `<AuthVideo>` component to stream local-path videos when Cloudinary is disabled (today Cloudinary is active so raw https URLs work).
- Pause the 10s Clubhouse poll when `document.hidden`.
- Add `max_length=2000` on FeedPostCreate.body.
- Timeout + error toast on stalled uploads in the composer.

## Iteration 47 (Feb 2026) — Tournament Bulk PDF Compiler

- **New `BulkScorecardPrintOverlay.jsx`** — director-only "Print All Tournament Scorecards" flow. Groups every scorecard on the round by its parent `card_id` (orphans bucketed under `__solo__`), renders one read-only green `<ScorecardGrid />` per group with a physical page-break between each (via a `.ac-bulk-card-group` class + `@media print { page-break-after: always }`), and auto-fires `window.print()` ~350ms after mount. Uses landscape letter for wide scorecards.
- **Button placement**: `data-testid="bulk-print-btn"` renders on BOTH the active view (top action row next to `scorecard-print-btn` and `recap-poster-btn`) AND the completed view (isCompleted early-return branch, next to `scorecard-print-btn`). Outline styling: `border-slate-700 text-slate-800 bg-white hover:bg-slate-100 rounded-full`. Gated by `isDirector && scorecards.length > 0` — non-directors and empty rounds never see it.
- **P0 invariant preserved**: the overlay renders the exact same `<ScorecardGrid />` component the completed-round view uses, so printed PDF == on-screen green grid == the platform's canonical scorecard format. Verified visually.
- **Testing** (`/app/test_reports/iteration_40.json`): 22/22 UI assertions PASS after fixing two flags from iteration_39 (missing button on completed view, duplicate testid). Backend pytest untouched — no backend changes this iteration.

## Iteration 44-46 (Feb 2026) — WS auth fix, scorecard zoning, dashboard palette overhaul

### Iter 44 · Fix "RECONNECTING…" polling loop
- **Root cause**: `_validate_ws_token` in `leagues_router.py` checked a legacy `session_token` row that Firebase auth never populates → every `/api/ws/rounds/{id}` handshake closed 4401 → client loop.
- **Fix**: verify the incoming query-string token via `_fb_get_current_user`, upsert via `_upsert_league_user`, keep the old `session_token` path as a fallback so dev tooling still works.
- **Coverage**: `tests/test_iteration44.py` opens a real WS with a Firebase idToken and asserts the hello frame + a `ping/pong` round-trip; a second test proves a garbage token still closes 4401.

### Iter 45 · RoundScorecard three-zone refactor
- **Top zone**: sticky header with Back button + new **"League Feed"** shortcut (`data-testid="go-to-league-feed-btn"`) → routes to `/leagues/{id}?tab=clubhouse`. `LeagueDetail.jsx` now honors `?tab=<key>` for initial-tab selection.
- **Middle zone**: LiveSimulator + FormatLeaderboard are wrapped in a single collapsible accordion (`scorecard-middle-zone` + `middle-zone-toggle` + `middle-zone-content`) so directors can focus on card builders below.
- **Bottom zone**: card builder + player grids (unchanged position).
- **Conditional unmount**: Sweep Finalize (`sweep-finalize-btn`) gated behind `isDirector && cards.length > 0`. The `isCompleted` early return still enforces the P0 rule — no simulators, no card builders, no hole nav, no sweep button — only the green ScorecardGrid + Print PDF + League Feed + Round Final badge.

### Iter 46 · League Dashboard palette + temporal round sections
- **Brand palette**: white page bgs, dark slate text, emerald accents throughout `LeagueDetail.jsx` + `ManagerDMPanel.jsx`.
- **Badge chip row**: replaced the flat metadata line with four white rounded chips carrying emerald icons — `league-chip-location`, `league-chip-players`, `league-chip-ace-pool`, `league-chip-bag-tag`.
- **Format + Director pills**: converted `chip-orange` and `chip-green` to inline emerald pill styles (Director pill now `bg-emerald-600 text-white` with a shield-check icon).
- **Rounds tab split into three temporal groups**:
  - `rounds-active-section` — priority card with emerald border + LIVE pulse pill + Open Scorecard / Finalize / Check-In QR buttons.
  - `rounds-upcoming-section` — minimalist white cards; empty state `rounds-upcoming-empty`.
  - `rounds-completed-section` — collapsible accordion (`rounds-completed-toggle`, `aria-expanded` wired) holding a compact list with a green `round-pdf-<id>` link.
- **Unified button system**:
  - **Primary** (Open Scorecard, New Round, Start, Broadcast, PDF Scorecard): `rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm px-4 py-2 shadow-sm`.
  - **Secondary** (Finalize, DM, Check-In QR): `rounded-full bg-white text-slate-800 border border-slate-300 hover:border-slate-500 font-semibold text-sm px-4 py-2`.
- **Tabs bar**: emerald pill for active, white outline for others.
- **Broadcast bar**: `ManagerDMPanel` Broadcast flipped to solid emerald (`bg-emerald-600` + `text-white`); DM stayed slate outline.

## Testing
- Backend pytest — **9/9 pass** (iterations 39-44 + regression suite).
- Frontend e2e via testing_agent — **21/21 assertions pass** (`/app/test_reports/iteration_38.json`); no critical or minor issues, no design flags.

## Backlog (P1/P2)
- **P3 — RoundScorecard.jsx & LeagueDetail.jsx are big** (~1100 + ~570 lines). Optional refactor: extract `<RoundCard variant="active|upcoming|completed" />` and split the scorecard's completed-round early-return into its own file.
- **P3 — Double-elim grand-final "bracket reset"** — still MVP single GF.
- **P3 — Recap poster Instagram share card** — 1080×1350 PNG twin.
- **P3 — LB drop toast** — "second life" copy when a player is bumped WB → LB.

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

---

## Iteration 53 — Throw Tracker offline-queue hardening + onboarding gate polish (2026-02-14)

### Fixed (P0)
- `ThrowTracker.jsx › flushOffline()` now `await load()` after ≥1 successful drain, so history refreshes without a page reload (matches Iteration 45 acceptance spec).

### Fixed (P1)
- `OnboardingGate.jsx` — the optional "Add a profile photo" step is now gated to `/feed` and `/profile` routes only. The required name step still runs everywhere. Unblocks click targets on `/throws`, `/vault`, and other feature pages.

### Hardened (P2 — Offline sync)
- Every queued throw carries a stable client-generated `Idempotency-Key`.
- Retry policy: exponential backoff per item (5s → 10s → 20s → … cap 5 min), poison-pill drop on 4xx server rejects, and drop after 12 attempts.
- Auto-drain drivers: window `online` event + 15 s heartbeat interval + explicit "Sync now" tap.
- Legacy queue entries are normalized on read (no data loss for users who already had un-synced throws).
- Backend `POST /api/throws` accepts `Idempotency-Key` header; duplicate replays return the original doc and skip re-insertion.

### Files touched
- `/app/backend/routers/throws_router.py` — added Idempotency-Key path.
- `/app/frontend/src/pages/ThrowTracker.jsx` — full rewrite of offline queue.
- `/app/frontend/src/components/OnboardingGate.jsx` — route-scoped photo step.

### Tests
- `tests/test_iteration53.py` — 3/3 pass (idempotent replay, no-key still creates two rows, key scoped per user).
- `tests/test_iteration52.py` — 3/3 still green (regression).

### Backlog (unchanged)
- P2: Division-Scoped Share Cards (one Leaderboard PNG per division).
- P2: Auto-Advance Live Toast on `bracket_advance` WS event.
- P2: Vault Share Sheets polish (richer card previews when sharing from Vault to Clubhouse).

---

## Iteration 54 — Division Share Cards on Completed Rounds (2026-02-14)

### Added
- `FormatLeaderboardPanel` — new director-only "Division cards · N" button that renders one 1080×1350 leaderboard PNG per division and triggers a download per card. Visible only when the round is Singles-format AND members span 2+ divisions. Works on both active and completed rounds.
- Each row on `FormatLeaderboardPanel` now shows a small division pill (Open/MPO/etc.) so managers can eyeball the grouping before generating the cards.

### Backend
- `GET /api/rounds/{id}/leaderboard` now returns `division` (defaults to `"Open"`) on every singles-mode row so the frontend can group and render division-specific graphics without a second round-trip.

### Files touched
- `/app/backend/routers/leagues_advanced_router.py` — division field on singles rows.
- `/app/frontend/src/components/FormatLeaderboardPanel.jsx` — full rewrite with share button + division pills.
- `/app/frontend/src/pages/leagues/RoundScorecard.jsx` — passes `isDirector`, `leagueName`, `roundName`, `acePool` to the panel.

### Tests
- `tests/test_iteration54.py` — 2/2 pass (division default `Open`, custom division echoes through leaderboard).

### Backlog (unchanged)
- P2: Auto-Advance Live Toast on `bracket_advance` WS event.
- P2: Vault Share Sheets polish (richer card previews when sharing from Vault to Clubhouse).

---

## Iteration 55 — Division Payout Cards (2026-02-14)

### Added
- **Payout share-card template** in `/lib/shareCard.js` — new 1080×1350 template that renders the top-5 projected payouts for a division with rank badge, name, score/plus-minus subtitle, cash amount, and "N% of pool" subtitle. Gold accent on 1st place.
- **`renderDivisionPayoutCards`** batch renderer — emits one PNG per division. Skips empty divisions and divisions with a $0 pool.
- **"Payout cards · N" button** inside `PayoutDistribution` modal (next to Finalize). Downloads one PNG per division whenever there's a non-zero pool.

### Payout distribution math (verified)
- Pool distributed proportional to # players per division.
- Within a division: 50/30/20 top-3 curve, with any leftover slice folded into 1st place when a division has fewer than 3 players. Solo player takes the whole division pool.
- All the client-side share card copy — cash amounts and pool percentages — mirrors what the server returns from `GET /rounds/{id}/payout`, so what the manager sees on the card is exactly what the ledger will post at Finalize.

### Files touched
- `/app/frontend/src/lib/shareCard.js` — new `renderPayoutTemplate` + `renderDivisionPayoutCards`; `renderShareCard` dispatch now supports `template: "payout"`.
- `/app/frontend/src/components/PayoutDistribution.jsx` — Payout cards button + safe-empty-catch cleanup.

### Tests
- `tests/test_iteration55.py` — 3/3 pass:
  - Pool distributes proportionally across 2 divisions (75/25 with 3+1 players).
  - 2-player division folds 3rd slice into 1st place (70/30).
  - Solo-player division takes 100% of pool.
- Full new-modules sweep (52/53/54/55): 11/11 pass.

### Backlog (unchanged)
- P2: Auto-Advance Live Toast on `bracket_advance` WS event.
- P2: Vault Share Sheets polish (richer card previews when sharing from Vault to Clubhouse).

---

## Iteration 56 — Finalize UI Freeze + Throw Tracker Nav CTA (2026-02-15)

### BUG 1 — Scorecard finalize freeze (fixed)
- `RoundScorecard.finalizeScorecard()` now, on server confirmation:
  - Clears certify-modal state (`certifyForScorecardId`, `certifyChecked`, `certifying`) inside a defensive try/catch.
  - Fires the success toast.
  - Redirects the user to `/leagues/{league_id}?tab=clubhouse` (the primary League Feed view) via `navigate(..., { replace: true })` so any local scorecard-refresh path can't trap the UI.
- **Kept intact**: Match-Play tie-break flow (director stays on the page when `bracket_advance.tied === true`), Match-Play champion confetti + advance toast, and the offline score queue in `/lib/offlineQueue.js` (unchanged — the redirect happens after the write is confirmed, not before, so no in-flight scores are lost).

### BUG 2 — Throw Tracker missing from nav (fixed)
- Added `/throws · Throw Tracker` to `NAV_ITEMS` in `Navigation.jsx` so it shows in both desktop and Chasers Hub mobile drawer.
- Added a **large touch-friendly outline CTA** at the top of the mobile Chasers Hub dropdown: `text-emerald-600` / `border-emerald-600` on white with `py-4`, rounded-xl, active:bg-emerald-50 for pressed feedback. `data-testid="nav-throws-cta-mobile"`.
- Registered `/throws` in `ROUTE_PREFETCHERS` so hover/touchstart warms the chunk.

### Files touched
- `/app/frontend/src/pages/leagues/RoundScorecard.jsx` — `finalizeScorecard` rewrite.
- `/app/frontend/src/components/Navigation.jsx` — NAV_ITEMS + mobile CTA + prefetcher.

### Testing
- Lint clean on both changed files.
- Backend unchanged — no new API contract.
- Offline queue in `/lib/offlineQueue.js` untouched; existing 3-test idempotency sweep still applies.

### Backlog (unchanged)
- P2: Auto-Advance Live Toast on `bracket_advance` WS event (broadcast side).
- P2: Vault Share Sheets polish.
- P2: Combined Post Bundle (Winner + Leaderboard + Payouts zip).
- P2: Payout Curve Presets at league level.
