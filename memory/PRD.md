# Ace Chasers — PRD

## Original problem statement
> Its a website it needs the profile preview to be what is seen as the public profile it should have the non-private data displayed exactly as it is now on the preview public profile need to add the element favorite frisbee option to the profile page when someone likes a profile they should go to a like page that will be in a separate tab.

## Follow-up requests
1. Replace mock login/signup with **real Firebase Authentication** (Email/Password + Google).
2. Wire Likes / Matches to a **real backend** (FastAPI + MongoDB). Seed the existing mock players as real DB users.
3. **Gated access**:
   - Soft email-verified banner (Firebase only) instead of hard-gate.
   - Env-toggled invite system. Codes optionally locked to a specific email. Single-use. Admin endpoints protected by a shared `ADMIN_API_KEY`.

## App overview
Ace Chasers is a disc-golf-themed swipe-to-match web app. Users sign in, swipe through other players, match on mutual likes, view their likes/matches, and manage their public profile.

## Architecture
- **Frontend**: React 18 + Vite 5, Tailwind, Zustand, React Router v6, firebase v10, axios.
- **Backend**: FastAPI + Motor (Mongo async). Firebase Admin SDK for ID-token verification (with dev decoded-only fallback).
- **DB**: Mongo collections — `users`, `swipes`, `matches`, `invites`.

## Implemented (Jan 2026)
### Session 1 — polish
- Restructured to `/app/frontend` + `/app/backend` (Vite + stub FastAPI).
- New `PublicProfilePreview` component → Profile view mode mirrors PlayerCard.
- `favoriteFrisbee` free-text field across Profile, PlayerCard, Discovery, Likes.
- `Likes` tab + route with match badges + Add Friend / Unlike actions.

### Session 2 — real auth + real backend
- `firebase_auth.py`: graceful init; verifies ID tokens when service account present, else decodes unverified (dev mode).
- `db.py`: Mongo singleton + indexes + `seed_demo_users` (Sarah/Jessica/Amanda).
- `server.py`: `auth/sync`, `users/me`, `discovery`, `swipes`, `likes`, `matches/{uid}/friend`, `likes/{uid}`. Mutual likes create canonical `matches` rows.
- Frontend: `lib/firebase.js` modular SDK; `lib/api.js` axios with auto-attached bearer token (Firebase or dev token); `AuthProvider` rehydrates the session on every load.
- `Login.jsx` / `SignUp.jsx` rebuilt for Firebase (email/password + Google). Dev fallback path mirrors the same UX before keys are configured.
- `matchStore` now API-backed.

### Session 3 — gated access
- **Email-verified soft banner** (`components/EmailVerificationBanner.jsx`): renders a yellow top banner with a "Resend email" button until the Firebase user verifies. Hidden in dev mode where verification doesn't apply.
- **`emailVerified` flag** added to `ProfileOut`; backend keeps `users.email_verified` in sync with token claims on every sync / `users/me`.
- **Invite system**:
  - `invites.py` — `create_invite`, `list_invites`, `revoke_invite`, `redeem_invite` (atomic single-use with email-lock support).
  - `POST /api/admin/invites`, `GET /api/admin/invites`, `DELETE /api/admin/invites/{code}` — protected by `X-Admin-Key` header (`ADMIN_API_KEY` env var).
  - `GET /api/config` — public flag (`require_invite`) consumed by the frontend on load.
  - `POST /api/auth/sync` — when `REQUIRE_INVITE=true`, new users must include a valid `invite_code`. Existing users are never re-gated.
  - Frontend Sign-Up shows an Invite Code field only when the server reports `require_invite: true`.
- **Session safety**: Login + SignUp now `commitSession()` — they only flip `isAuthenticated` after `/auth/sync` succeeds, and roll back the Firebase / dev session on failure so blocked users stay on the form with a visible error. `AuthProvider` rehydrate does the same on reload.

## API surface (`/api`)
- `GET  /health`
- `GET  /config`
- `POST /auth/sync`  body: `{invite_code?}`
- `GET  /users/me` · `PUT /users/me`
- `GET  /discovery`
- `POST /swipes` · body: `{target_uid, action: "like"|"pass"}`
- `GET  /likes` · `DELETE /likes/{target_uid}`
- `POST /matches/{target_uid}/friend`
- **Admin (X-Admin-Key required)**: `GET/POST/DELETE /admin/invites[/{code}]`

## Verified flows (Playwright + curl)
1. Signup → discovery → like seeded players → mutual matches surfaced.
2. Likes page Add Friend persists, Unlike removes likes + match.
3. Profile edit saves Favorite Frisbee + every other field via the API.
4. Invite gating with `REQUIRE_INVITE=true`:
   - Signup without code → `invite_code required` error, stays on form.
   - Wrong email + email-locked code → `Invite is locked to a different email address`.
   - Correct redemption → enters app.
   - Reuse of the same code → `Invite already used` error, stays on form.
5. Admin endpoints: create / list / delete invites via curl with `X-Admin-Key`.

### Session 4 — Feed (Jan 2026)
- Posts collection (`posts`) with `body`, `image_path`, `visibility ('public'|'friends_only')`.
- `/api/feed` cursor-paginated; visibility honors mutual-friend matches.
- Compose UI with client-side canvas compression + magic-byte sniffing backend-side.
- Discovery card surfaces author's latest public post.
- Dismissible alpha-banner (localStorage gated).

### Session 5 — Video posts + friend-request flow (Feb 2026)
- **Video posts**: `/api/posts` now also accepts a `media` field carrying mp4/webm/quicktime up to 25MB. Backend sniffs container magic bytes (`ftyp`, EBML), persists alongside images via a new `video_path` column, and surfaces `video_url` on `PostOut`. Feed compose box gains a 🎬 Video button + inline `<video controls>` preview; existing photo flow untouched.
- **Friend-request system**: new `friend_requests` Mongo collection with three endpoints —
  - `POST /api/friend-requests/{target_uid}` (auto-friends if reverse pending / reverse like exists)
  - `POST /api/friend-requests/{from_uid}/accept`
  - `POST /api/friend-requests/{from_uid}/decline`
- **`GET /api/inbox`**: aggregates pending friend requests + incoming likes (de-duped against mutual matches and pending FRs).
- **Discovery redesign**: now a responsive 1/2/3-column grid. **Pass button removed.** Cards expose ❤️ Like (records a like only) and 🤝 Friend (sends a friend request).
- **Likes page**: now has three sections — friend requests received (Accept/Decline), people who liked you (notification list with quick "Send friend request"), and your outgoing likes.

## API surface (`/api`) — updated
- `GET  /health` · `GET /config`
- `POST /auth/sync`  body: `{invite_code?}`
- `GET  /users/me` · `PUT /users/me` · `GET /users/{uid}`
- `POST /users/me/profile-picture` · `POST /users/me/banner`
- `GET  /discovery`
- `POST /swipes` · `GET /likes` · `DELETE /likes/{target_uid}` · `POST /matches/{target_uid}/friend`
- **NEW** `POST /friend-requests/{target_uid}` · `POST /friend-requests/{from_uid}/accept` · `POST /friend-requests/{from_uid}/decline`
- **NEW** `GET /inbox`
- `GET  /feed` · `POST /posts` (image OR video) · `DELETE /posts/{id}`
- **Admin** (X-Admin-Key): `GET/POST/DELETE /admin/invites[/{code}]`

### Session 6 — Durable storage + refactor + pagination (Feb 2026)
- **Cloudinary integration**: profile pictures, banners, post images, and post videos now persist on Cloudinary (cloud `bangingchains`). New `/app/backend/cloud_storage.py` helper. Backend uploads bytes directly to Cloudinary *after* magic-byte sniffing. `image_path` / `video_path` in Mongo now store full Cloudinary HTTPS URLs; `_hydrate_post` keeps backward-compat with legacy `/api/uploads/<file>` paths.
- **`sniff_video_mime` brand whitelist**: only accepts `isom / iso2-6 / mp41 / mp42 / avc1 / M4V  / dash / mmp4 / qt ` ftyp brands. Rejects `.3gp`, `.heic`, `.heif`, `.avif`, `.f4v`.
- **Discovery cursor pagination**: `/api/discovery` now returns `{ players, next_cursor }`. Page size 24. Frontend gets a "Load more players" button (`data-testid=discovery-load-more-btn`) that appends pages.
- **Backend refactor**: `server.py` shrunk from 858 → 90 lines. Pydantic models moved to `models.py`, shared helpers to `deps.py`, and all routes split across six modules in `routers/` (auth, admin, media, discovery, social, posts).

### Session 7 — Geocoding + distance filter + UI consistency (Feb 2026)
- **Geocoding (`/app/backend/geocode.py`)**: Free-text `location` is geocoded via Nominatim (OpenStreetMap, no API key) and cached in Mongo `geocode_cache`. Profile saves auto-write `lat`/`lng` on the user doc.
- **`/api/discovery?radius_miles=N`**: filters candidates by haversine distance from the caller's stored coords. Each player in the response carries `distance_miles` when the filter is active.
- **Discovery UI**: new radius bar with chips (Anywhere / 10 / 25 / 50 / 100 / 250 mi). Distance shown inline next to each card's location. Helpful hint appears when the caller hasn't set their own location yet.
- **UI button consistency**: all 3 Discovery card actions (Nice / Message / Player) now use the same text-disc-green styling as the Feed compose Photo and Video buttons.
- **Feed compose**: new 👍 Nice quick-insert button (`data-testid=compose-add-nice-btn`) styled identically to Photo / Video. Click appends "Nice! 🥏" to the body.
- **Tests**: 12 new tests (4 in test_geocode.py, 8 in test_iteration4.py) — all green.

## API surface (`/api`) — updated
- `GET  /discovery?radius_miles=N` — now also returns `distance_miles` per player when filter is active.

### Session 8 — Comment previews + re-engagement banners (Feb 2026)
- **`recent_comments` on posts**: `/api/feed` and `/api/users/{uid}/posts` now return up to 3 newest comments per post (chronological), batched via a single Mongo aggregation per page — no N+1.
- **Inline comment preview**: each post card on the Feed shows the 3-comment preview without expanding the full thread. "View all N comments" link appears when the count exceeds 3. Preview hides while the full thread is open.
- **DismissibleBanner component**: new reusable `<DismissibleBanner>` with `localStorage`-backed lazy-init dismissal (no flicker).
- **Welcome banner on Feed**: "We've upgraded! Let's get you re-connected:" — prompts users to set location, add a profile photo, and post a hi.
- **Invite banner on Discovery**: "Loving the app? Bring your friends!" — encourages sharing.
- **Tests**: 3 new tests (`test_iteration5.py`) — all green. Full suite: 80 pass, 3 skip, 5 pre-existing seed failures unchanged.

### Session 9 — Discovery template unification + Interested-in field (Feb 2026)
- **Discovery card template = "How others see you" card.** Discovery grid cards now reuse the exact `<PublicProfilePreview>` component used on the Profile page, including the full banner + overlapping circular avatar + bio fields. Action buttons (Nice / Message / Player) are passed in via a new optional `actions` slot.
- **Responsive grid**: 1 col mobile / 2 col md (≥768px) / 3 col xl (≥1280px).
- **New `interestedIn` profile field**: free-text (max 200 chars), with a privacy toggle behaving identically to the existing private fields. Backend `PRIVATE_FIELDS` extended in `deps.py`; `ProfileIn`/`ProfileOut` updated; `DiscoveryProfile` inherits the field automatically.
- **Tests**: 3 new tests (`test_iteration6.py`) — all green. Full suite: 83 pass, 3 skip, 5 pre-existing seed failures unchanged.

### Session 10 — Interested-in chip filter + full messaging UX (Feb 2026)
- **Interested-in filter chip set** on Discovery (Casual / Doubles / League / Tournaments / Putting + Any). Backend `/api/discovery?interested_in=keyword` does case-insensitive substring match and excludes players who marked the field private.
- **`MessageComposeModal` (new reusable component)**: clicking 💬 Message on a Discovery card or PlayerProfile opens an inline compose modal instead of navigating to the inbox. Send & stay on page.
- **Messages inbox revamp**: header now has a ✏️ New button; empty state shows both an inline link and a primary CTA. Both open the modal in `pickFromFriends` mode (search box + friend list rows). After picking + sending, the new thread is auto-selected and the threads list refreshes.
- **Tests**: 5 new tests (`test_iteration7.py`) — all green. Full suite: 88 pass, 3 skip, 5 pre-existing seed failures unchanged.

### Session 12 — Friend-request notifications (Feb 2026)
- **🔔 Bell + red badge** in the navbar (data-testid=notifications-bell-btn). Badge shows pending friend-request count, capped at "9+".
- **Popover panel** with each request as `notifications-request-{uid}` — avatar, name, **✓ Add** and **✕ Ignore** inline buttons. Click outside closes. "View all on Likes page →" footer link.
- **Inline toast** ("X wants to add you") fires top-right for 5s when a NEW uid appears between polls. Tracked in localStorage `ace_seen_friend_request_uids_v1` so we never re-toast.
- **One-shot session modal** "Add Player? (N)" on first auth-ready when requests pending. sessionStorage `ace_friend_requests_session_modal_shown` prevents repeat.
- **Browser Notification API** opt-in (button only renders when `Notification.permission === 'default'`). Fires native browser notifications on new arrivals if granted.
- **Inbox polling** tightened from 60s → 30s for faster freshness.
- Backend untouched; everything builds on the existing `/api/inbox`, `POST /friend-requests/{uid}/accept|decline`.

### Session 13 — Seed purge + comment Nice reactions (Feb 2026)
- **Seed/demo users filtered everywhere they could surface**: `/api/discovery`, `/api/inbox.incoming_likes`, `/api/likes`, `/api/friends` all now exclude `is_seed: true` users at query time. `POST /api/auth/sync` no longer calls `ensure_inbound_likes_for`, so fresh signups never receive seed auto-likes.
- **Per-comment 👍 Nice**: new `POST /api/posts/{post_id}/comments/{comment_id}/nice` toggle. `CommentOut` gained `nice_count` + `liked_by_me`. Counts come through on both `/api/feed.recent_comments` AND `GET /api/posts/{id}/comments` via a single batched `_attach_comment_reactions` aggregation.
- **Cascade delete**: deleting a comment also wipes its `post_comment_likes`.
- **Frontend `PostInteractions`**: comment Nice button (data-testid=comment-nice-btn-{commentId}) with optimistic UI + rollback, count chip (comment-nice-count-{commentId}) only when > 0. New "👍 Nice!" quick-insert button (comment-insert-nice-{postId}) appends `Nice! 🥏` to the comment textarea.
- **Tests**: 9 new tests (5 in test_iteration10.py + 4 in test_iteration10_extra.py from the testing agent) — all green.

### Session 14 — "Most niced this week" Feed badge (Feb 2026)
- **`GET /api/feed/top-niced-this-week`**: aggregation across `post_likes` for the past 7 days that joins on `posts`, filters to public + non-disc_review entries, and returns the single top post (or null when none qualify).
- **Feed badge UI**: gold-trimmed card pinned to the top of `/feed` (data-testid=top-niced-banner) that shows author avatar, body preview, 👍 count, and timeAgo. Click jumps to `#post-{id}` (smooth-scroll via `scroll-mt-24`).
- **Tests**: 3 new tests (`test_iteration11.py`) — top winner contract, friends-only exclusion for non-friends, disc-review exclusion — all green.

## Backlog / next steps (current)
- P2: Native Web Share / copy-link CTA on the Discovery invite banner.
- P2: Real-time message delivery via Firestore listener or websockets so receivers don't have to refresh threads.
- P2: Re-enable seed_demo_users behind a DEV-only env flag so the 5 carry-over seed tests in test_api.py go green.
- P2: Wrap `cloud_storage.upload_bytes` in `asyncio.to_thread()` for true non-blocking uploads.
- P2: DRY the "upload to cloud OR disk" branching between media_router and posts_router.
- P2: Replace ADMIN_API_KEY with Firebase custom claims (`admin: true`).
- P3: Real-time notifications (Firestore listener / websockets).

## Backlog / next steps
- P2: Optional one-shot migration of `/app/backend/uploads/` legacy files to Cloudinary, then drop the StaticFiles mount.
- P2: Wrap `cloud_storage.upload_bytes` in `asyncio.to_thread()` for true non-blocking uploads (current SDK is sync).
- P2: DRY the "upload to cloud OR disk" branching between `media_router` and `posts_router` into a single helper in `cloud_storage.py`.
- P2: Geocoding currently runs synchronously inside PUT /users/me; move to a background task if profile saves become hot.
- P2: Re-enable seed_demo_users behind a DEV-only env flag so the 5 seed-dependent tests in test_api.py go green on a fresh DB.
- P2: Replace `ADMIN_API_KEY` with Firebase custom claims (`admin: true`).
- P2: Admin web UI for invites instead of curl.
- P3: Real-time notifications via Firestore listener or websockets.


