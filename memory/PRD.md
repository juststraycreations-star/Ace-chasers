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

### Session 15 — Incomplete-profile placeholders fixed (Feb 2026)
- **Real root cause** of "placeholder cards" on production: not `is_seed: true` users (there are zero of those!), but rather **abandoned signups that never set a `name`**. Preview DB had 104 of 115 users with no name set.
- **Fix**: Discovery + Likes + Inbox + Friends queries now require `name: {$nin: [None, ""]}` in addition to the existing `is_seed != true` filter. Real users with a completed profile only.
- **Tests**: 2 new tests (`test_iteration12.py`) — nameless user hidden, empty-string name hidden, named user visible. All green.

### Session 16 — Mandatory onboarding name gate (Feb 2026)
- **`OnboardingGate.jsx` (new)**: blocking modal mounted by `App.jsx` whenever `authReady && isAuthenticated && profile && !profile.name.trim()`. No dismissal paths — no ESC, no overlay click, no close button. Calls `PUT /api/users/me` on submit, closes only after the server returns the saved name.
- **Eliminates empty placeholders at the source**: combined with iter-12's backend `name` filter, no user can ever sit invisible in a half-onboarded state. Existing users with no name set will see the gate on their next visit and be forced to fix it.
- **Tests**: 13/13 frontend acceptance criteria verified end-to-end by the testing agent (signup → no name → gate visible on every authed route → cannot dismiss → save → gate gone permanently).

### Session 17 — 2-step onboarding (name + photo) (Feb 2026)
- **`OnboardingGate.jsx` now a 2-step flow**:
  1. **Name (blocking, undismissable)** — same contract as iter-13. Save advances to step 2 instead of closing.
  2. **Photo (optional)** — '📷 Pick a photo' uses `compressImage` + multipart upload to `POST /api/users/me/profile-picture`. 'Skip for now' closes the gate without an upload.
- **`sessionStorage.ace_onboarding_photo_step_done`** tracks the photo step so a refresh doesn't bounce the user back, but clears on tab close so a returning user the next day gets one more nudge.
- **Header + step indicator** swap between steps. Both steps remain undismissable.
- **Tests**: 22/22 acceptance checks green across two Playwright phases (nameless user → step 1 → step 2 → Skip; existing named user with no photo → step 2 → real Cloudinary upload).

### Session 18 — Courses page + in-app reviews + Ace Club field (Feb 2026)
- **Backend**: New `routers/courses_router.py` with 8 endpoints (list/search, detail, recent-reviews, per-course-reviews, create-review with one-per-user upsert, delete-review, admin add/delete). New `seed_courses.py` seeds 15 popular US courses on first boot. New `CourseIn` / `CourseOut` / `CourseReviewIn` / `CourseReviewOut` Pydantic models.
- **"Ace Club" field** — bool + optional integer count on every course. 10 of the 15 seeded courses ship with Ace Club enabled (Maple Hill 250, Idlewild 180, Winthrop Gold 320, etc).
- **Frontend `/courses`** — list with search (250ms debounce), recent-reviews sidebar, Ace Club pills on enabled courses.
- **Frontend `/courses/:id`** — detail page with star picker, write-a-review form, last 10 reviews, replace-on-resubmit, admin/author delete.
- **Nav** — new "Courses" link between Bag Check and Discovery.
- **Tests**: 6/6 backend tests + 30+/30+ frontend acceptance checks green.

### Session 19 — Ace Club on player profile cards (Feb 2026)
- **`aceClub: bool` + `aceClubCount: int?`** added to `ProfileIn` / `ProfileOut` / `user_to_profile`. Same shape as the course-level field for consistency.
- **`PUT /api/users/me`** auto-clears `aceClubCount` whenever `aceClub` is set to false — no stale ace count can linger.
- **Frontend Profile edit form**: new toggle '🏆 I&apos;m in an Ace Club' (data-testid=profile-ace-club-toggle) + conditional number input (data-testid=profile-ace-club-count-input). Unchecking the toggle clears the count via UI + server.
- **`PublicProfilePreview`** renders a gold pill (data-testid=public-profile-ace-club) below the player's name when `aceClub` is truthy. Shows on Discovery cards, PlayerProfile, and the "How others see you" preview.
- **Tests**: 4/4 new tests in `test_iteration16.py` — self lookup, other viewer lookup, Discovery card carry-through, toggle-off clears count. All green.

### Session 20 — Disc golf news rail on Feed (Feb 2026)
- **Backend `routers/news_router.py` (new)**: pulls RSS from Ultiworld Disc Golf (`discgolf.ultiworld.com/feed`), PDGA (`pdga.com/news/feed`), and r/discgolf top-of-week (`reddit.com/r/discgolf/top/.rss?t=week`). 30-minute in-memory TTL cache; httpx + feedparser; per-URL dedupe; newest-first.
- **`NewsResponse` + `NewsItem` Pydantic models** in `models.py`.
- **Dependency**: `feedparser==6.0.12` added to `requirements.txt`.
- **Frontend `NewsSidebar.jsx` (new)**: 📰 Disc Golf News rail. Each item is an external link with source pill, title, summary, and time-ago.
- **Feed layout reflow**: `max-w-7xl` flex container — left column is the existing feed (capped at `max-w-2xl`), right column is the news rail (`hidden xl:block`, sticky). On smaller screens the rail stacks below the feed via `xl:hidden` mirror.
- **Tests**: 2/2 new tests in `test_iteration17.py` — feed aggregation contract + URL dedupe. All green using FastAPI `TestClient` with patched httpx + startup hooks.

### Session 21 — Daily Plastic full-page tab + PDGA RSS fix (Feb 2026)
- **Removed top-nav "Likes" link**. The `/likes` route stays (NotificationsBell + SessionRequestsModal link to it) but it's no longer a primary nav surface — the bell + session modal handle the Add Player flow.
- **`/daily-plastic` (new full-page route)**: '📰 Daily Plastic' header + 'Updated …' freshness label + source filter chips (All / Ultiworld / PDGA / r/discgolf) + 2-col responsive grid of news cards (open in new tab).
- **PDGA RSS URL update**: `pdga.com/news/feed` started returning 404; swapped to `pdga.com/rss.xml`. Backend now logs a warning when any source returns zero entries.
- **Dropped Feed's mobile-stacked news section**: Daily Plastic is the primary news destination now; the xl+ sticky news rail on Feed stays for ambient discovery.
- **Tests**: existing 2/2 test_iteration17.py still green. Frontend acceptance for Daily Plastic + nav swap 100% in iteration_18.json.

### Session 22 — Article thumbnails on news cards (Feb 2026)
- **Backend `_extract_thumbnail()`**: tries 4 image sources per RSS entry in reliability order — `media:thumbnail`, `media:content` (type=image), RSS `<enclosure type="image/*">`, then first `<img src="…">` from the HTML description/content. Returns null when none found.
- **`NewsItem.thumbnail_url`**: new optional field on `/api/news` payload. Live cache shows 8/24 items currently have thumbnails (mostly PDGA).
- **Daily Plastic cards**: 16:9 cover image renders above the title when present; cards gracefully fall back to text-only when the image 404s or no thumbnail was found.
- **Feed news rail**: 56×56 square thumbnail next to each headline for the sticky right-rail variant.
- **No new tests required**: the field is additive; existing 2/2 tests in test_iteration17.py still green.

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


