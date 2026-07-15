# Ace Chasers · Disc Golf League Platform · PRD

## Original Problem Statement
Build a Full-Stack Disc Golf League Platform Extension for Ace Chasers. Central relational schema linking four core concepts: **Leagues, Seasons, Rounds, Players**. Four modules within a unified dashboard:

1. **League Dashboard & Operations** – multi-step Create-League wizard (Name, Location, Format toggle: Singles / Random-Draw Doubles / BYOP / Team), recurring season schedule generator, debit/credit ledger (Ace Pool, CTP cash, Club Payouts).
2. **Digital Scorecard & Check-In** – live interactive scorecard, player scoring, card selection, real-time multiplayer updates, "Proof of Score" edit log, in-scorecard text/emoji chat, QR-code check-in generator.
3. **Standings & Handicap Engine** – automated leaderboard with customizable win-allocation formula, rolling Bag Tag matrix (re-sorts on round completion), rolling handicap engine (avg last 5 rounds).
4. **Private Clubhouse Feed** – authenticated chronological feed exclusive to league members, Pinned Announcements header, Lost & Found sub-tab with image uploads, auto-generated Hot Round / Most Improved recap cards, vertical Story Grid.

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn/ui + Phosphor icons + qrcode.react + framer-motion. Auth via httpOnly cookie + Bearer header fallback. Polling every 5–10s for realtime.
- **Backend**: FastAPI + Motor (async MongoDB). All routes under `/api`. Auth via Emergent Google OAuth (session_id → session_token exchange). Object storage via Emergent Object Storage.
- **DB Collections**: `users`, `user_sessions`, `leagues`, `league_members`, `seasons`, `rounds`, `cards`, `scorecards`, `proof_logs`, `chat_messages`, `announcements`, `lost_found`, `stories`, `feed_posts`, `ledger`, `files`.

## User Personas
- **League Director** – creates and configures leagues, schedules rounds, manages ledger, posts announcements, finalizes rounds.
- **Player / Member** – joins leagues, plays rounds, sees standings, bag tag, shares stories.

## Implemented (v1 – Feb 15, 2026)
- ✅ Emergent Google Auth (session cookie + Bearer)
- ✅ Object storage upload/download with soft-delete
- ✅ Multi-step Create League wizard (Identity → Format → Season → Payouts)
- ✅ Recurring schedule generator (auto-creates Rounds)
- ✅ Debit/Credit ledger with per-category totals (Ace Pool auto-tracks league.ace_pool)
- ✅ Live scorecard with hole-by-hole scoring, color-coded cells (birdie/eagle/bogey/double+)
- ✅ Proof-of-Score audit log (per-hole edit history)
- ✅ Card selection + card builder
- ✅ In-scorecard chat (per card, polling)
- ✅ QR code check-in generator (client-side)
- ✅ Automated leaderboard with configurable win_points + points_step
- ✅ Rolling Bag Tag matrix (framer-motion animated re-sort)
- ✅ Handicap engine (avg last 5 rounds plus/minus)
- ✅ Finalize-round → awards points, swaps bag tags, generates Hot Round + Most Improved recap FeedPost
- ✅ Private Clubhouse Feed (director-gated announcements + member posts)
- ✅ Pinned announcements (urgent variant)
- ✅ Lost & Found with image uploads + resolve toggle
- ✅ Vertical Story Grid (48h TTL)
- ✅ Landing page with modern-sporty hero aesthetic

## Test Results (Iteration 1)
- Backend: 29/31 pytest cases pass (~93.5%)
- Frontend: ~95% – all core flows verified
- File upload verified working after retest (transient storage failure during first pass)

## P0 / P1 Backlog (Next Iterations)
- P1: WebSocket-based realtime (replace polling)
- P1: PDGA-style handicap normalization + course rating
- P2: Team scoring templates (Random-Draw Doubles auto-pair on check-in)
- P2: CSV exports of standings + ledger
- P2: Push notifications for announcements
- P2: Player profile page with round history + trends chart
- P2: Photo lightbox for stories and Lost & Found
- P2: Sub-leagues / divisions (Am / Pro)
