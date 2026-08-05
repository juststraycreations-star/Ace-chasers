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

### Session 23 — Mobile responsive Navigation (Feb 2026)
- **Bug**: 9 nav items (Feed, Bag Check, Courses, Discovery, Daily Plastic, Messages, Profile, Bell, Logout) were rendered in a single non-responsive flex row → overflow / unusable layout on phones.
- **Fix** (`/app/frontend/src/components/Navigation.jsx`): split into desktop (`hidden lg:flex`) and mobile (`flex lg:hidden`) clusters. Mobile cluster shows the notifications bell + a hamburger toggle (`data-testid="nav-mobile-toggle"`) which expands a slide-down panel (`data-testid="nav-mobile-panel"`) with all 7 nav links and a Logout button. Active link is highlighted in `disc-gold/20`. Panel auto-closes on route change.
- **Accessibility**: hamburger button has `aria-label`/`aria-expanded`, focus ring on `disc-gold`.
- **Verified** at 375px (mobile) and 1440px (desktop) viewports via screenshot tool — desktop layout unchanged.


## Backlog / next steps (current)
- P2: Native Web Share / copy-link CTA on the Discovery invite banner.

### Session 24 — Launch Giveaway promo + Cache-notice modal (Feb 2026)
- **Giveaway promo card** (`/app/frontend/src/components/GiveawayPromo.jsx`) — gold-bordered card on Login page above the form. Copy: "🏆 LAUNCH GIVEAWAY — Win a GTO Leopard3, Proto Glow, & Pro Series Duo Pack!". 2-step entry instructions + drawing date Sunday, July 19, 2026.
- **Cache-notice → modal** (`/app/frontend/src/components/CacheNoticeModal.jsx`) — replaced inline `<CacheNotice />` banner on Login page with a modal that auto-opens on first failed login attempt. Dismissable via ✕ / Escape / backdrop / "Got it" button. localStorage flag `ace_cache_notice_dismissed_v1` prevents it from reappearing after dismissal. SignUp page still uses the original inline `CacheNotice` (untouched).
- **Backend perf refactor (session 23 follow-up applied this session also):** N+1 `_hydrate_post` → batched `_hydrate_posts` in `/app/backend/routers/posts_router.py`, plus projection fixes on `social_router.py` (lines 169, 351), `posts.py:111`, and `posts_router.py:235`. 12/12 backend tests pass (iteration_19.json). Deployment agent: PASS, ready for production.
- **SEO/social previews:** Added meta description, OG, Twitter Card, Schema.org JSON-LD (Organization + WebSite + WebApplication) to `index.html`. Added `/public/og-image.jpg` (1200×630 sunset basket), `/public/robots.txt`, `/public/sitemap.xml`.

- P2: Real-time message delivery via Firestore listener or websockets so receivers don't have to refresh threads.
- P2: Re-enable seed_demo_users behind a DEV-only env flag so the 5 carry-over seed tests in test_api.py go green.
- P2: Wrap `cloud_storage.upload_bytes` in `asyncio.to_thread()` for true non-blocking uploads.

### Session 25 — User-facing "Add a course" on Courses page (Feb 2026)
- **Backend** (`/app/backend/routers/courses_router.py`): new `POST /api/courses` endpoint open to any signed-in user. Dedupes on name+location (case-insensitive, anchored regex). Stores `submitted_by` uid for moderation. Legacy admin `/api/admin/courses` endpoint still works unchanged.
- **Frontend**: new `AddCourseModal.jsx` component (name, location, holes, description, Ace Club checkbox + count). New "Add a course" button (`data-testid="add-course-btn"`) at top of `/courses` page. Success path: toast + new course prepended to the list. Duplicate path: in-modal error message, modal stays open.
- **Verified** via `/app/test_reports/iteration_20.json` — 10/10 new backend tests, 12/12 i19 regression still green, frontend e2e for add + duplicate-error flows.

- P2: DRY the "upload to cloud OR disk" branching between media_router and posts_router.
- P2: Replace ADMIN_API_KEY with Firebase custom claims (`admin: true`).
- P3: Real-time notifications (Firestore listener / websockets).

## Backlog / next steps

### Session 26 — "Suggested by" credit on community-added courses (Feb 2026)
- **Backend** (`/app/backend/models.py` + `/app/backend/routers/courses_router.py`): `CourseOut` now exposes optional `submitted_by_name`. New batched helper `_attach_submitter_names(courses)` resolves submitter uids → display names in a single `users.find` per page. Wired into `GET /api/courses`, `GET /api/courses/{id}`, and `POST /api/courses` (inline). The POST handler now reads the name from MongoDB (not Firebase token claims), since email/password signups set their name via PUT /api/users/me which only writes to Mongo.
- **Frontend**: `Courses.jsx` and `CourseDetail.jsx` render an italic `🥏 Suggested by {name}` line under each user-submitted course. Admin-seeded courses (no `submitted_by`) leave the field null and the line is hidden.
- **Tests:** 30/30 backend tests pass across iter19/20/21. New file `/app/backend/tests/test_iteration21.py` covers the named user, anon submitter (no profile name), admin-seed, and POST inline-response paths.

- P2: Optional one-shot migration of `/app/backend/uploads/` legacy files to Cloudinary, then drop the StaticFiles mount.
- P2: Wrap `cloud_storage.upload_bytes` in `asyncio.to_thread()` for true non-blocking uploads (current SDK is sync).
- P2: DRY the "upload to cloud OR disk" branching between `media_router` and `posts_router` into a single helper in `cloud_storage.py`.
- P2: Geocoding currently runs synchronously inside PUT /users/me; move to a background task if profile saves become hot.
- P2: Re-enable seed_demo_users behind a DEV-only env flag so the 5 seed-dependent tests in test_api.py go green on a fresh DB.
- P2: Replace `ADMIN_API_KEY` with Firebase custom claims (`admin: true`).

### Session 27 — Desktop video playback fix + Post edit/delete (Feb 2026)
- **Video codec bug fixed** (`/app/backend/cloud_storage.py`): iPhone-recorded HEVC/.mov videos wouldn't play on desktop Chrome/Firefox because those browsers lack HEVC support. New helper `browser_compatible_video_url()` rewrites Cloudinary video URLs to insert `f_mp4,vc_h264` after `/upload/`, forcing Cloudinary to transcode on-the-fly to a universally-compatible MP4/H.264 stream. `_hydrate_posts` in `posts_router.py` wraps every returned `video_url` through the helper. Non-Cloudinary URLs pass through unchanged; already-transformed URLs are not double-injected. Feed.jsx `<video>` also gained `playsInline` for iOS in-line playback.
- **Post edit + delete feature**: New PATCH `/api/posts/{id}` endpoint (Pydantic `{body: str, 1-1000 chars}`) using `motor.find_one_and_update` with `ReturnDocument.AFTER`. Sets `edited_at` ISO timestamp. `PostOut.edited_at: Optional[str]` added to models. Owner-only (`{id, author_uid}` filter). Frontend Feed.jsx: header shows Edit + Delete for is_mine posts, Edit reveals an inline textarea with Save/Cancel; saved posts show a subtle `(edited)` indicator with the timestamp on hover.
- **Testing**: 44/44 backend (14 new + 30 regression) + 5/5 frontend e2e (iter22). Zero issues found.

- P2: Admin web UI for invites instead of curl.

### Session 28 — Video compression + compose-side poster preview (Feb 2026)
- **Cloudinary compression** (`/app/backend/cloud_storage.py`): extended the video transform from `f_mp4,vc_h264` → `f_mp4,vc_h264,q_auto`. Cloudinary now picks the best bitrate/quality for the requesting client → smaller files, faster loads on mobile/cellular. Idempotency guard broadened to `"/upload/f_mp4,"` so old-transform URLs from prior deploys aren't double-injected.

### Session 29 — PWA install foundation + Google Play prep (Feb 2026)
- **Clean app icon**: replaced watermark-baked og-image with a programmatically-drawn disc-green + gold basket silhouette (`make_icon` in gen script). No URLs/text — Google Play icon-guideline compliant. 11 sizes + 2 maskable variants + apple-touch-icon + 3 favicons in `/app/frontend/public/icons/`.
- **PWA files**: `manifest.webmanifest` (id, start_url, scope, display=standalone, disc-green theme, 3 shortcuts to Feed/Discovery/Daily Plastic), `service-worker.js` (app-shell precache, stale-while-revalidate for static, cache-first for Cloudinary, never caches `/api/`), `registerSW.js` (auto-registers on prod builds, skipped in Vite dev). `index.html` gained all mobile-web-app / apple-touch / theme-color meta tags and manifest link.
- **TWA / Digital Asset Links**: `/app/frontend/public/.well-known/assetlinks.json` template served at `/.well-known/assetlinks.json` (200, application/json). Ready for PWABuilder → paste in the SHA-256 fingerprint from the Android build. README next to it documents the substitution.
- **Alpha banner removed**: deleted `/app/frontend/src/components/AlphaBanner.jsx` and its Feed.jsx wiring.
- **"Get the app" banner**: new `/app/frontend/src/components/GetTheAppBanner.jsx` shows at top of Feed after sign-in. Dismissible (localStorage `ace_get_the_app_dismissed_v1`). Falls back to "coming to Google Play" when the `PLAY_STORE_URL` constant is empty; once the Play listing is live, changing that constant makes the banner a working link with an "Install" pill.

- **Compose-side video preview improvement** (`/app/frontend/src/lib/videoPoster.js` + `Feed.jsx`): the compose preview `<video>` now uses `preload="none"` + `playsInline`, so the browser doesn't buffer the whole file into memory on mobile just to render a preview. New helper `extractVideoPoster(file)` uses an off-screen `<video>` + canvas to grab a JPEG poster frame client-side (data URL), which is wired to the compose `<video poster=…>` for an instant visual preview. Helper is best-effort with a 4s timeout — falls back to the previous black tile if decoding fails (never regresses).
- **Testing**: iteration_22 tests updated for the new transform string; **45/45 backend tests pass** across iter19-22. Poster extraction verified live on a signed-up user's compose form (`preload="none"` confirmed in DOM). Screenshot verified compose renders correctly.

### Session 30 — Discovery count bug fix (Feb 2026)
- **User-reported bug**: "Why does the '24 players to discover' number never change?" — the count on /discovery stayed stale even after adding friends or sending player requests.
- **RCA**: `/api/discovery`'s `exclude` set was only populated from the legacy `db.swipes` collection. The current UI uses `friend_requests` (Player button) and `matches` (accepted requests) — neither wrote to `swipes`, so nothing ever dropped out of the deck.
- **Fix** (`/app/backend/routers/discovery_router.py` lines ~66-95): `exclude` set now unions three sources — legacy swipes, `friend_requests` (both incoming and outgoing), and `matches` (both directions user_a/user_b). Self remains excluded.
- **Frontend**: no change. Discovery already refetches deck on mount and on filter change, so the corrected count surfaces on next visit/filter toggle. In-session UX preserved (card stays visible with status pill updating Player → ⏳ Sent → ✓ Players).
- **Tests**: iteration_23 — 9 new + 45 regression = **54/54 passing**. Report: `/app/test_reports/iteration_23.json`.
- **Known limitation**: `.limit(1000)` on each exclusion source is fine at current scale but a power user with >1000 friends/requests could see stale entries. Fix later with pagination or `$unionWith` aggregation if scaling.


- P3: Real-time notifications via Firestore listener or websockets.




### Session 31 — Discovery count in-session fix (Feb 2026)
- **Bug re-reported**: user said "The count on the discovery page is still stuck at 24 — it only works when you click to view more pages." Iteration 23 only fixed the backend exclude set; the frontend still rendered `deck.length` (which never decreased in-session because cards intentionally stay visible after a Sent request).
- **Fix** (`/app/frontend/src/pages/Discovery.jsx` L199-217): header count now derives from `deck.filter(p => !friendSet.has(p.uid) && !sentSet.has(p.uid)).length`. `matchStore.sendFriendRequest` already optimistically updates `inbox.sent_friend_request_uids`, so the derived count re-renders immediately on successful send. Added `data-testid="discovery-count"` for testability.
- **Backend**: no change this iteration; iteration 23 exclude-set fix still active.
- **Verified**: `/app/test_reports/iteration_24.json` — desktop + mobile e2e confirmed count decrements immediately (24 → 23 → 22) with Sent pills appearing on the previously-actioned cards. **54/54 backend regression green**.


### Session 32 — Discovery page size fix (Feb 2026)
- **User re-reported**: "It is still not counting the players correctly, I know there should be more than 24 users." Screenshot showed acechasers.net/discovery capped at exactly 24.
- **RCA**: The endpoint had `DISCOVERY_PAGE_SIZE = 24` as the default page size. Even with 88+ real users in Mongo, the API returned exactly 24 per fetch. Pagination via `next_cursor` + "Load more" existed but wasn't obvious to users.
- **Fix** (`/app/backend/routers/discovery_router.py`): bumped `DISCOVERY_PAGE_SIZE` 24 → 100, max limit cap 50 → 200, radius-scan cap 200 → 800. All users on a small/launching community now fit on the first fetch. Pagination cursors still work for when the user base grows past 100.
- **Verified on preview**: /discovery header now reads "88 players to discover" (was 24). No Load-more button needed. 45/45 iter19-22 regression tests still green.


### Session 33 — Full merge with disc-leauge-ops (Feb 2026)
- **User request**: merge the disc-leauge-ops league/tournament management app into Ace Chasers as a unified product (Option A, "go big").
- **Scope shipped**: ~1,618 lines of new backend + 6 pages + 13 components + 46 shadcn/ui + 52 npm deps, in one session.
- **Auth bridged**: league app's Emergent OAuth cookie sessions → Firebase Bearer via new `_upsert_league_user()` helper mapping `uid` → league `user_id`. Old `/auth/session` and `/auth/logout` endpoints removed; `/auth/me` retained.
- **Storage bridged**: Emergent object storage → Cloudinary via `put_object`/`get_object` compat shims in `routers/leagues_router.py`. `/api/files/upload` returns both `path` and `url`; `/api/files/{path}` 302s to the Cloudinary URL. `db.files` schema gained `url`.
- **Frontend integration**: new `context/AuthContext.jsx` bridges Firebase Zustand store → league `useAuth()`. Vite gained `@` path alias + `optimizeDeps.esbuildOptions.alias` + `optimizeDeps.include: ['react-is']`. `lib/api.js` gained named `API` export. Routes: `/leagues`, `/leagues/new`, `/leagues/:id`, `/leagues/:id/players/:userId`, `/rounds/:roundId`. Nav "Leagues" tab added.
- **Verified via screenshot**: `/leagues` renders LeagueDashboard with empty state, zero page errors, backend router responds to authenticated Firebase requests.
- **Follow-ups**: testing-agent regression pass on merged app; theme reconciliation (league dark/orange vs Ace Chasers disc-green); route the LeagueLanding page; add tests for 40+ new API routes.


### Session 34 — League theme reconciliation & redirect fix (Feb 2026)
- Verified iter 25 regression fix: League nav buttons no longer redirect to /feed. Root cause was auth bridge duplicate-key (E11000) on `users.uid` + 5 stale `/dashboard`/`/create-league` route strings; testing agent patched both.
- Background colors on all imported league pages switched from black → white to match Ace Chasers.

### Session 35 — Legal compliance UI + backend enforcement (Feb 2026)
- **User request**: integrate legal compliance wrappers, disclaimers, and terms of service text UI components into League Dashboard and Ledger views.
- **Ledger Privacy Disclaimer**: new `/app/frontend/src/components/LedgerDisclaimer.jsx` reused inside `CreateLeague.jsx` step-4 payouts and `LedgerTab.jsx`. Copy: "Ace Chasers provides an automated calculation ledger utility. Real-world financial pool management and payouts are the sole responsibility of the League Director." Links to `/legal/privacy`.
- **Legal page**: new `/app/frontend/src/pages/legal/Privacy.jsx` at route `/legal/privacy` (public, works signed-out). Four sections: Ledger Utility Disclosure, Proof of Score Audit Trail, Fair Play Terms · Private Clubhouse, Data & Privacy.
- **Scorecard Submission Certification** (frontend): `RoundScorecard.jsx` — each active scorecard row now has `finalize-btn-{sc.id}`. Clicking opens `finalize-modal` with `finalize-cert-checkbox` (required copy: "I certify that these scores are accurate. I understand that submitting updates the automated digital Bag Tag matrix and logs my user ID in the Proof of Score audit trail."). `finalize-confirm-btn` stays disabled until checkbox is ticked. Row shows `finalized-badge-{sc.id}` after success.
- **Scorecard Certification** (backend, `leagues_router.py`):
  - `Scorecard` model gained `finalized`, `certified`, `certified_by_user_id`, `certified_by_name`, `certified_at`.
  - NEW `POST /api/scorecards/{scorecard_id}/finalize` with `{certified: bool}` payload. Rejects `certified=false` with 400 "Certification required...". On success writes cert fields + a ProofLog audit entry + WS broadcast.
  - `PATCH /api/scorecards/{id}/score` now returns 409 "Scorecard already finalized" if the row is locked.
- **Clubhouse First-Time Fair Play Agreement**:
  - `LeagueMember` model gained `clubhouse_agreed` (default false) and `clubhouse_agreed_at`.
  - NEW `POST /api/leagues/{league_id}/clubhouse/agree` persists the flag + timestamp.
  - `GET /api/leagues/{league_id}` exposes `my_clubhouse_agreed` for the current user.
  - New `ClubhouseAgreementModal.jsx` overlays the Clubhouse tab until the member clicks "I Agree"; persistent per-league.
- **Iter 25 follow-ups shipped**: `LeagueDashboard.jsx` load() now uses `Promise.allSettled` so a failing `/leagues/browse` doesn't kill the dashboard; `AppHeader.jsx` trophy shadow rgba(255,92,0) → rgba(245,197,66); `LeagueLanding.jsx` + `VictoryCard.jsx` orange rgba/`#FF5C00` remnants swapped to disc-gold.
- **Verified**: `/app/test_reports/iteration_26.json` — 10/10 new backend tests + prior 64/64 regression green. Zero bugs.

## Prioritized backlog
- **P1** — Wire the Clubhouse Agreement modal for other private surfaces (Announcements-only view, DM invites) that share the same trust model.
- **P1** — Add "finalize round" (director-level) sweep action that requires certification of all cards in one modal.
- **P2** — Convert `ProofLog` schema to include an explicit `event_type` field (score_edit / certification / director_note) instead of overloading `hole=0` + name suffix.
- **P2** — Break `leagues_router.py` (1,700+ lines) into `league_seasons`, `league_rounds`, `league_ledger`, `league_clubhouse` submodules.
- **P2** — Integrate Sentry for production error tracking (needs user DSN).
- **P3** — Real-time notifications via Firestore listener or websockets for non-round events.

### Session 36 — Create-League P0 fix + Sweep-Finalize + DM Fair Play + Router refactor Phase 1 (Feb 2026)
- **User report**: "Why can I not create a test league in preview — when you click create it loops you back to the create page just blank." + follow-ups on the roadmap.
- **P0 ROOT CAUSE FOUND & FIXED**: 3 pre-existing user docs had `email: None` and 170 had `name: None`. On every `/api/leagues*` call, `_upsert_league_user` returned the doc, and Pydantic `User(email: str)` threw a `ValidationError` → 500 → the frontend toast fired and the wizard stayed put. Root fix: `leagues_router.py` `_upsert_league_user` now coerces `email: None` → `""` on both the existing-user backfill branch and initial insert branch. Backfilled dirty docs directly in Mongo (3 email:None + 170 name:None).
- **Sweep-Finalize (director sweep)**: NEW `POST /api/rounds/{round_id}/finalize` with `{certified: bool, complete_round: bool}` — director-only, rejects `certified=false` with 400, certifies all open scorecards, stamps `certified_by_name` with `DIRECTOR SWEEP`, writes one ProofLog audit row per card with `edited_by_name` containing `DIRECTOR SWEEP-CERTIFIED`, optionally marks the round completed. Frontend: `sweep-finalize-btn` (director-only) + `sweep-finalize-modal` listing every card with per-card certified/open state, `sweep-cert-checkbox` (mandatory), `sweep-complete-round-checkbox` (defaults on).
- **Extended Clubhouse Agreement**:
  - Hoisted `ClubhouseAgreementModal` from `ClubhouseTab.jsx` up to `LeagueDetail.jsx` — now covers Announcements-only viewers plus any private tab (Rounds/Standings/Ledger/Clubhouse) on first visit.
  - NEW `ProfileOut.dmTermsAgreedAt` field on the user profile.
  - NEW `POST /api/users/me/dm-terms/agree` endpoint (idempotent, returns full ProfileOut).
  - `MessageComposeModal.jsx` now shows `dm-terms-gate` + `dm-terms-agree-btn` for the first outbound DM invite. Send button disabled until agreement is captured.
- **leagues_router Refactor Phase 1**: Extracted the Clubhouse content endpoints (announcements, lost-found, stories, feed) into `leagues_clubhouse_router.py` (174 lines) — same `api_router` instance is reused so URL surface is unchanged. Circular-import safely resolved by placing the submodule import at the bottom of `leagues_router.py`. Monolith shrunk 1804 → 1681 lines.
- **Verified**: `/app/test_reports/iteration_27.json` — 15/15 new backend + full P0 E2E in Chromium (fresh signup → wizard → `/leagues/{id}` navigation confirmed, no blank loop). Iter 25/26 baselines preserved. Zero bugs.

## Prioritized backlog (post-Session-36)
- **P1** — Refactor Phase 2: extract Ledger (POST/GET/CSV export + entry-fee escrow) + Rounds/Scorecards into their own submodules. Estimated 2 phases.
- **P1** — DM invite gate: add the same `dmTermsAgreedAt` prompt to reply-flows (currently only guards the first outbound-from-compose modal).
- **P2** — Compliance Dashboard for directors: per-league metrics (% cards certified this round, Fair Play agreement recency, unresolved lost & found, ledger deltas).
- **P2** — ProofLog schema: add explicit `event_type` (score_edit / individual_certify / director_sweep) instead of overloading `hole=0` + name suffix.
- **P2** — Sentry error tracking (needs user DSN).
- **P3** — Real-time notifications for non-round events.


### Session 37 — Growth investigation + Giveaway removal + Report Bug + Perf split (Feb 2026)
- **User asks**: (1) "make sure there's no reason more players can't join" (2) take down disc giveaway (3) add "report a bug" on /leagues (4) investigate slow page loads.
- **Growth investigation**: Ran end-to-end production signup against `https://acechasers.net` — Firebase Identity Toolkit `signUp` + `/api/auth/sync` + `/api/users/me` + `/api/discovery` + `/api/feed` all return 200 in ~2 seconds for a fresh account. **No code-level blocker on new signups.** The user's "no new players in a while" observation is a marketing / discovery / funnel problem, not a code problem.
- **Giveaway removed**: Deleted `GiveawayPromo` import + `<GiveawayPromo />` render from `Login.jsx`. The banner no longer shows on the login page.
- **Report Bug**: New `ReportBugButton.jsx` component opens `mailto:juststraycreations@gmail.com` with a pre-filled subject and body containing the current page URL, user agent, and timestamp. Injected in the `/leagues` dashboard toolbar next to the "New League" button (per user's "only on /leagues" request). Not visible anywhere else.
- **Slow-load root cause + fix — HUGE win**: The whole app was shipping as ONE 1,318 KB JS bundle (365 KB gzip) with no code splitting. Converted every page in `App.jsx` to `React.lazy()` + `<Suspense fallback={...}>`. Added `vite.config.js` `build.rollupOptions.output.manualChunks` that groups node_modules into 8 vendor buckets:
  - `vendor-react` (150KB / 48KB gz) — react + react-dom + react-router, cached across pages
  - `vendor-firebase` (164KB / 33KB gz) — Firebase Web SDK
  - `vendor-icons` (134KB / 32KB gz) — Phosphor + Lucide
  - `vendor-charts` (292KB / 80KB gz) — **Recharts + D3, only downloads when user visits a chart-using page (Ledger tab)**
  - `vendor-radix`, `vendor-ui`, `vendor-query`, `vendor`
  - **Result: initial JS = 51 KB (14 KB gz)** — down from 1,318 KB (a 96% reduction on the critical path). Each route is now its own 3-40 KB chunk downloaded on demand.
- **Verified**: `/app/test_reports/iteration_28.json` — 8/8 backend + full frontend E2E, zero bugs. Prior iter 26/27 baselines untouched.

## Prioritized backlog (post-Session-37)
- **P1** — Refactor Phase 2: extract Ledger + Rounds/Scorecards from `leagues_router.py` into submodules.
- **P1** — DM Fair Play gate for reply flows.
- **P1** — Growth: invite-friend flow (share a signup link, badge reward on referral).
- **P2** — Compliance Dashboard for directors.
- **P2** — Sentry integration (needs user DSN).
- **P2** — ProofLog `event_type` schema.
- **P3** — Real-time notifications for non-round events.


### Session 38 — Perceived-perf fixes (Feb 2026)
- **User complaint**: "when you click on the page it takes ages to load" (production).
- **Investigation**: prod bundles now ship ~209 KB gzip on initial load and APIs return in 100-300ms. Not a code/network bottleneck — the felt-slowness is **blank screen during (a) lazy-chunk download + (b) data fetch**.
- **Fix 1 — Nav hover/focus/touch prefetch (`Navigation.jsx`)**: added `ROUTE_PREFETCHERS` map (feed/bagcheck/courses/leagues/discovery/daily-plastic/messages/profile) + module-level `prefetched` Set for dedup. Every `<Link>` (both desktop and mobile) now warms the target chunk on `onMouseEnter` / `onFocus` / `onTouchStart` so by the time the user clicks, the JS is already cached. Feels instant.
- **Fix 2 — Skeleton loaders (`Skeletons.jsx`)**: new `FeedSkeleton`, `PlayerGridSkeleton`, `LeagueGridSkeleton` using Tailwind `animate-pulse`. Shapes mirror real content → CLS=0. Wired into `Feed.jsx` (3 placeholders), `Discovery.jsx` (8 placeholders), `LeagueDashboard.jsx` (4 placeholders) replacing the old plain "Loading feed…" / "LOADING…" text.
- **Verified**: `/app/test_reports/iteration_29.json` — 100% pass. Hover triggers new module requests in Vite dev, prod build still emits per-route chunks (verified via `yarn build`), all 3 skeletons render during in-flight fetch with correct testids, 11/11 lazy routes render authenticated content, report-bug-btn regression green.

## Prioritized backlog (post-Session-38)
- **P1** — Refactor Phase 2: extract Ledger + Rounds from `leagues_router.py`.
- **P1** — Invite-friend flow (referral link + badge) — highest-leverage growth lever.
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Compliance Dashboard for directors.
- **P2** — Sentry integration (needs user DSN).
- **P2** — ProofLog `event_type` schema cleanup.
- **P3** — Real-time notifications for non-round events.


### Session 39 — Create Round + Self-serve Join Round + Full League Audit (Feb 2026)
- **User report (production)**: "In leagues why can I not create a card — nothing happens when I click". Two root causes uncovered:
  - **P0 #1**: `LeagueDetail.jsx` Rounds tab had **no "New Round" button at all** — a director had no way to schedule rounds through the UI even though `POST /api/leagues/{id}/rounds` had existed on the backend since the original merge.
  - **P0 #2**: The backend `POST /api/rounds/{id}/cards` endpoint is director-only, so a regular player could not create a card for themselves to join an existing round.
- **Fixes shipped**:
  - **Create Round modal**: `LeagueDetail.jsx` now fetches `/api/leagues/{id}/seasons`, exposes a director-only `new-round-btn` (top-right on Rounds tab) plus a `rounds-empty-create-btn` inside the empty state. The `new-round-modal` collects name / date / holes (9/18/24/27) / optional course_rating, POSTs to `/api/leagues/{id}/rounds` using `seasons[0].id`, then navigates the director straight to `/rounds/{new_id}`.
  - **NEW self-serve endpoint** `POST /api/rounds/{round_id}/join` in `leagues_router.py`. Creates (or reuses, idempotently) a solo Card labeled `{FirstName}'s Card` + a Scorecard with 18 zeros + the member's computed handicap. `_require_member` gate → non-members get 403. WS broadcasts `player_joined` on non-idempotent create.
  - **Frontend `join-round-btn`**: `RoundScorecard.jsx` empty-state now shows "Join this round · create my card" for league members with no scorecard yet. Directs the player straight into scoring.
- **Full League Audit (per user request)** — testing agent iter 30 confirmed every league surface operational:
  - Create League wizard → seeds Season + director LeagueMember ✅
  - Join League → creates player LeagueMember ✅
  - Browse public leagues, Standings, Ledger (POST/GET/CSV export) ✅
  - Clubhouse (announcements, lost-found, stories, feed) — all endpoints post-refactor ✅
  - Score editing + individual finalize (rejects `certified=false`) + Sweep-finalize ✅
  - CTP, Payouts, Auto-pair, Bag Tag matrix ✅
  - DM Fair Play gate, Report Bug button, all 11 lazy routes ✅
- **Verified**: `/app/test_reports/iteration_30.json` — 16/16 backend pytest + 14/14 frontend UI assertions, zero bugs. Naming nit only (`new-round-*-input` testids are prefixed vs the review spec's bare names — acceptable). Design note: onboarding profile-photo prompt + Clubhouse Fair Play modal stack on first league visit — each has its own dismiss CTA, acceptable UX.

## Prioritized backlog (post-Session-39)
- **P1** — Refactor Phase 2: extract Ledger + Rounds from `leagues_router.py`.
- **P1** — Invite-friend referral flow (still the highest-leverage growth lever).
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Compliance Dashboard for directors.
- **P2** — Sentry integration (needs user DSN) — would have caught the "vendor-react useState" P0 before users did.
- **P2** — ProofLog `event_type` schema.
- **P3** — Real-time notifications for non-round events.
- **P3** — Test-user cleanup sweep job (many `TEST_*@example.com` docs left behind by iter runs).



### Session 40 — Open Google Group beta invite + resend-to-all + security cleanup (Feb 2026)
- **User asked**: "I made the Google Group open — update the invitations to point people to join the group themselves, then resend to all existing users."
- **Root state on arrival (from handoff)**: prior agent had partially edited backend + admin UI but left both `beta_router.py` and `Beta.jsx` with syntax-breaking leftover fragments from failed search-replaces. Backend was in a soft-broken state; frontend Beta page had duplicated tail code.
- **Fixes shipped**:
  - `backend/routers/beta_router.py`
    - Removed leftover stale block after `invite_all_users_to_beta` (was breaking SyntaxError on reload).
    - Rewrote plain + HTML email template around the **open Google Group** (`GOOGLE_GROUP_URL` env). Step 1 tells users to click "Join group" (no approval needed); Step 2 tells them to click Play install with the same Google account.
    - `POST /api/admin/users/beta-invite-all?force=true` re-emails **every** user; without `force` it still skips already-notified addresses. Return payload now includes `force_resend` flag.
    - Fixed `get_current_user_wrapper` — import was pointing at non-existent `verify_firebase_token`; corrected to `verify_token` and wrapped in try/except so bad tokens now return **401** (previously 500).
  - `frontend/src/pages/Beta.jsx`
    - Removed the duplicated fragment tail (was causing JSX syntax error).
    - Success screen now renders **Step 1 — Join the Google Group** (dark-green primary CTA, `data-testid=beta-google-group-link`) and **Step 2 — Install from Google Play** (yellow CTA, existing `beta-play-opt-in-link`). Copy is fully self-service — no "wait for invitation" wording remains.
    - Landing hero copy updated to describe the two-step install.
  - `frontend/src/pages/BetaTestersAdmin.jsx` (already had, kept intact)
    - `Invite new users` button → `POST /admin/users/beta-invite-all` (skips already-invited)
    - `Resend to ALL` button → `POST /admin/users/beta-invite-all?force=true` (with confirm dialog)
    - `Users CSV` + `Testers CSV` exports.
  - **Security cleanup**: removed publicly-served `/app/frontend/public/downloads/android.keystore`, `KEYSTORE_PASSWORD.txt`, and `play-console-keys.txt` (user confirmed they have local copies). Only the release `.aab` bundles remain.
- **Verification**:
  - Backend curl: unauth invite-all → 401; bad-token invite-all → 401; signup returns `email_sent: true` for a controlled recipient (christina.ann.washburn@gmail.com); second signup with same email is idempotent (`already_signed_up: true`, no duplicate send).
  - Frontend Playwright: `/beta` submission surfaces success screen with both correct hrefs — `https://groups.google.com/g/ace-chasers-beta-testers` and `https://play.google.com/apps/testing/acechasers.net`.
  - Python lint: clean. JS lint: only pre-existing `react/no-unescaped-entities` warnings (not introduced by this session).
  - **Not** triggered during debug: the bulk `Resend to ALL` action — that's reserved for the user to press from the admin UI in production.
- **User security follow-ups (not yet done, user action required)**:
  1. Rotate the Gmail app password because it was disclosed in previous chat history.
  2. Confirm private Android signing key/password are stored locally (public copies now deleted).

## Prioritized backlog (post-Session-40)
- **P0** — User to press "Resend to ALL" in production after preview review + deploy.
- **P1** — Rotate Gmail app password + update `GMAIL_APP_PASSWORD` in backend `.env`.
- **P1** — Refactor Phase 2: extract Ledger + Rounds from `leagues_router.py`.
- **P1** — Invite-friend referral flow (still the highest-leverage growth lever).
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Compliance Dashboard for directors.
- **P2** — Sentry integration (needs user DSN).
- **P2** — ProofLog `event_type` schema.
- **P3** — Real-time notifications for non-round events.
- **P3** — Bulk-email audit log (actor, count, timestamp, failures).

### Session 41 — First Run founding member badge + Leagues nav pulse + Chasers Hub button + Dashboard layout refactor + card-creation UX fix + v1.0.3 AAB (Feb 2026)

**Big-picture:** Landed 6 tightly-linked upgrades in one iteration. All were tested by the iteration_31 testing agent — 17/17 backend pytest + 10/10 UI assertions passed.

**Backend**
- `models.py` — `ProfileOut` extended with `firstRun`, `hasDismissedFirstRunModal`, `hasViewedLeaguesFeature` booleans.
- `deps.py` — `user_to_profile` maps the three new mongo fields onto the response model.
- `routers/auth_router.py`:
  - `/api/auth/sync` now awards `first_run: true` at insert time when `count_documents({is_seed: {$ne: True}}) < 100`. Semantics match the backfill contract exactly.
  - New `POST /api/users/me/dismiss-first-run` and `POST /api/users/me/dismiss-leagues-feature` — auth-gated, flip the relevant boolean and return the fresh profile. Bad/absent tokens → 401.
- `server.py` — new `_backfill_first_run_flag()` runs at startup. Idempotent: sets `has_dismissed_first_run_modal` / `has_viewed_leagues_feature` defaults on every user missing them; awards `first_run: true` to the earliest 100 non-seed users by `created_at`. Boot log confirmed "First Run backfill complete: 100 founding members" on 313-user DB.

**Frontend components (new)**
- `components/FirstRunBadge.jsx` — 16–20px inline SVG chip: slate-900 bg, amber-500/30 border, three concentric flight rings + centre dot. Tooltip on hover reads "First Run: One of the first 100 players to card up."
- `components/FirstRunWelcomeModal.jsx` — one-shot congrats overlay. Renders only when `profile.firstRun && !profile.hasDismissedFirstRunModal`. Big 72px badge, "Welcome to the First Run" header, benediction copy, "Let's Play" CTA. Close = POST /dismiss-first-run + optimistic patch. Mounted globally in `App.jsx` when `isAuthenticated`.
- `components/LeaguesFeatureAnnouncement.jsx` — pulsing amber basket icon (custom disc-golf basket SVG). Only renders when `profile.hasViewedLeaguesFeature === false`. Click opens compact dropdown with heading "Disc Golf Leagues Are Live! 🏆" + body copy + "Check Out Leagues →" CTA. CTA (and clicking the Leagues nav link directly) both call POST /dismiss-leagues-feature and clear the pulse permanently.

**Frontend components (updated)**
- `components/Navigation.jsx`:
  - Mobile hamburger is now a proper pill button with `bg-slate-800/80`, backdrop-blur, `border-slate-700` → `hover:border-amber-500`, hover scale + active compression, and a small `text-xs uppercase tracking-wider font-semibold` **"Chasers Hub"** label right of the icon lines.
  - `LeaguesFeatureAnnouncement` renders inline next to the Leagues desktop link, and standalone in the mobile right-cluster.
  - Clicking the Leagues nav link (any device) auto-dismisses the pulse via `dismissLeaguesPulseIfNew`.
- `components/ReportBugButton.jsx` — added `variant="muted"` for footer placements (tiny slate-500 text-only style, no border, no uppercase pill).
- `pages/Profile.jsx` — `FirstRunBadge` (20px) renders next to display name only when `profile.firstRun`.
- `pages/leagues/LeagueDashboard.jsx` — full restructure:
  - Zone 1: Header (title + subline) on gray-50 canvas.
  - Zone 2: **Single primary-action white card** hosting ONLY the "New League" button. No duplicate creation entries anywhere on the page.
  - Zone 3: League list, each row a **bounded white card** (`border-gray-100`, subtle shadow, hover amber tint). Left column = league name + location + player count (vertical descriptive stack). Right column = format chip + Ace Pool amount (justified-right metric stack).
  - Zone 4: Browse public leagues (separated by hr divider).
  - **Footer**: `border-t` + centred quiet `ReportBugButton variant="muted"`. Bug link is nowhere near the primary workflow.

**Card creation UX fix** (this was the real user-reported "card creation is broken" bug — API was fine, UI was misleading)
- `pages/leagues/RoundScorecard.jsx`:
  - `new-card-btn` is now `disabled` for non-directors with an explanatory `title`. Previously non-directors could tap it and got a raw 403 toast — that's what looked like a broken bug to them.
  - `createCard()` guards on: not-director → helpful toast pointing them to "Join this round"; empty label → toast; empty players → toast; in-flight click → no-op. Adds `creatingCard` spinner state so the "Create Card" button shows "Creating…" and is disabled while the POST is pending. Success surfaces a "Card created" toast.

**Performance profile of league APIs** (per iteration_31 testing agent)
- All league endpoints p95 < 200ms server-side. Slowness perception is NOT backend. Root causes:
  1. First-request Firebase token cold-verification (~300–500ms).
  2. Frontend sometimes issues 5+ sequential GETs on mount despite `Promise.all` where present. LeagueDetail already parallelises; other pages could benefit.
- **Backlog** — bundle endpoint `GET /api/leagues/{id}/dashboard` returning league+seasons+rounds+standings+ledger in a single trip.

**Android v1.0.3 release build (paused pending user)**
- `build/twa/app/build.gradle`: `androidbrowserhelper 2.6.2 → 2.7.2` (removes deprecated `Window.setStatusBarColor` / `setNavigationBarColor` calls Play Console flagged for Android 15). `minSdkVersion 21 → 23` (required by 2.7.2). `versionCode 3 → 4`, `versionName 1.0.2 → 1.0.3`.
- `build/twa/twa-manifest.json` — same version bumps.
- Rebuilt AAB via `./gradlew bundleRelease` (JDK 17 + `qemu-user-static` + `libc6-amd64-cross` reinstalled since ephemeral container was clean).
- **Old keystore password lost** → generated a fresh upload keystore, exported `.pem` cert, signed the AAB with the new key. Files staged in `frontend/public/downloads/` for the user to grab and then delete:
  - `acechasers-net-v1.0.3.aab` (signed with new upload key)
  - `upload-keystore.jks` + `NEW_UPLOAD_KEYSTORE_PASSWORD.txt` (save forever)
  - `upload_certificate.pem` (submit via Play Console → App integrity → "Request upload key reset")
  - `README.txt` (step-by-step)
- User is currently working on their side to download + request the upload-key reset. Google reset approval typically 1–2 business days.

**Beta invite flow with open Google Group** (from Session 40, retained)
- Corrected `GOOGLE_GROUP_URL` to `https://groups.google.com/g/ace-chasers-beta-testers/about`.
- Rotated Gmail app password (old one was exposed in earlier chat).
- Email template + `/beta` success screen + admin `Resend to ALL` all reflect open Google Group self-service.
- Not yet deployed — still holding for user review before production push.

## Prioritized backlog (post-Session-41)
- **P0** — Deploy Session 40 + 41 changes to prod once user confirms beta email preview.
- **P0** — User to submit `upload_certificate.pem` for Play upload-key reset, then upload `acechasers-net-v1.0.3.aab` to Closed Testing.
- **P1** — After Play reset lands, press "Resend to ALL" from admin dashboard.
- **P1** — League dashboard bundle endpoint (`/api/leagues/{id}/dashboard`) to shrink the frontend waterfall.
- **P1** — Extract Ledger + Rounds from `leagues_router.py` (phase 2 refactor).
- **P1** — Invite-friend referral flow — highest-leverage growth lever.
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Sentry (needs user DSN).
- **P2** — Compliance dashboard for directors.
- **P2** — Bulk-email audit log.
- **P2** — ProofLog `event_type` schema.
- **P3** — Real-time notifications for non-round events.


### Session 42 — Founding-member recount + Dashboard bundle endpoint (Feb 2026)

**User feedback that drove this iteration:**
- The iter31 backfill mistakenly counted test-agent accounts (QA `@example.com` users) toward the "First 100" tier, awarding 100 badges when reality was ~40 real users.
- User asked to cap the tier at **40** and exclude testing-agent accounts.
- Also asked to build the recommended `/api/leagues/{id}/dashboard` bundle endpoint to fix the frontend waterfall.

**Backend changes**
- `server.py` `_backfill_first_run_flag()` — refactored:
  - `FOUNDING_LIMIT = 40` (was 100).
  - Real-user filter now excludes emails matching `^(test|qa_|demo_|bgtest|btnclk|testi|testjoiner)` and `@example.com$`.
  - No longer conditional: RESETS `first_run=false` on every non-winner uid so misfires from concurrent test runs get swept on the next boot. Log line format now: `First Run backfill complete: N founding members (of R real users, limit=40)`.
- `routers/auth_router.py`:
  - New module-level `_TEST_EMAIL_RE` regex + `_is_test_email(email)` helper (single source of truth shared with backfill contract).
  - `auth_sync()` now short-circuits: if the current signup's OWN email matches `_TEST_EMAIL_RE`, `is_first_run` stays false. Fixes the iter32 bug where test signups incorrectly claimed badge slots between backend restarts.
- `routers/leagues_router.py` — new `GET /api/leagues/{league_id}/dashboard` endpoint bundling league + seasons + rounds + members using `asyncio.gather`. Non-members receive the same league shape with empty sub-arrays + accurate `member_count` for the join CTA.

**Frontend changes**
- `pages/leagues/LeagueDetail.jsx` — `load()` now issues a single `GET /leagues/{id}/dashboard` instead of 4 parallel GETs. No behavior change from the user's perspective, just fewer network round-trips.

**Verification (iter32 → iter33)**
- iter32 hit 13/15 pytest — flagged the auth_sync gating bug.
- Fixed in this session, iter33 hit 13/13 pytest.
- **Dashboard bundle perf: 4.91× faster than the previous 4 sequential GETs (p50 118.9ms vs 584.1ms).**
- Exact data-shape parity with the individual endpoints (verified by set-equality on ids/keys).
- Preview DB confirmed at exactly **3 founding members** (Christina + 2 Kitty Google-auth users). Production DB will award 37–40 real users on next backend boot.

**Remaining known nits (not blocking)**
- Concurrent-signup race on the founding gate — two racers reading `count=39` could both flip `first_run=true`. Fine at current traffic; consider atomic `$inc` counter before scaling.
- DRY nit: `auth_sync` has an inline copy of the test-email regex string for the Mongo `$regex` filter and also references the compiled `_TEST_EMAIL_RE`. Could consolidate via `_TEST_EMAIL_RE.pattern`.

## Prioritized backlog (post-Session-42)
- **P0** — Deploy Sessions 40/41/42 to prod once user OKs the beta email preview.
- **P0** — User to submit `upload_certificate.pem` for Play upload-key reset, then upload `acechasers-net-v1.0.3.aab`.
- **P1** — After Play reset lands, admin presses "Resend to ALL".
- **P1** — Extract Ledger + Rounds from `leagues_router.py` (phase 2 refactor).
- **P1** — Invite-friend referral flow.
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Sentry (needs user DSN).
- **P2** — Compliance dashboard for directors.
- **P2** — Bulk-email audit log.
- **P2** — Atomic founding-member counter for high-concurrency signups.
- **P3** — Real-time notifications for non-round events.


### Session 43 — Ledger router extract + Compliance dashboard (Feb 2026)

**User asks:**
- Refactor Ledger (and eventually Rounds) out of the 1,795-line `leagues_router.py` monolith.
- Build a director-only Compliance Board so sweep-finalize never stalls silently.

**Ledger refactor (phase 2 of router split)**
- New file `backend/routers/leagues_ledger_router.py` hosts the 4 endpoints previously buried in `leagues_router.py`:
  - `POST /leagues/{id}/ledger`
  - `GET /leagues/{id}/ledger`
  - `GET /leagues/{id}/ledger.csv` (supports `?auth=` query param for browser downloads)
  - `POST /leagues/{id}/entry-fees/collect` (70/20/10 auto-split)
- Attaches handlers to the SAME `api_router` instance via `from .leagues_router import api_router, db, get_current_user, _require_member, LedgerEntry, _csv_response`. URL surface, prefix, auth semantics unchanged.
- `leagues_router.py` tail-import block now registers three sub-routers in order: clubhouse, ledger, compliance.
- `LedgerCreate` and `EntryFeePayload` Pydantic models moved with their endpoints.

**Compliance Board (new)**
- New file `backend/routers/leagues_compliance_router.py` with one director-only endpoint:
  - `GET /leagues/{id}/compliance`
- Returns a single JSON blob with two sections:
  1. **`clubhouse_terms`** — `agreed_count`, `outstanding_count`, `outstanding_members[]`. Members who haven't tapped "Agree" on the Clubhouse Fair Play modal.
  2. **`rounds[]`** — per-round scorecard certification. For each round: `scorecard_total`, `certified_count`, `finalized_count`, `pending_certification[]` (with member_id, member_name, bag_tag, scorecard_id, finalized flag, certified_by_director flag, player_certified flag), and `can_sweep_finalize: bool` (`true` iff every scorecard is certified via director OR player-certified OR already-finalized).
- Frontend `components/ComplianceTab.jsx` — new director-only tab on League Detail. Renders:
  - Big amber % ring + progress bar for Clubhouse agreement rollup.
  - Chip list of members who haven't agreed yet.
  - Card per round with certification progress, colored green when ready to sweep-finalize.
  - Blocking chips per pending player with badge status (`NO CERT` / `PLAYER OK` / `FINAL`) and hover-title explanation. "Open Round" button jumps straight to the round scorecard page.
- Only mounted for `league.is_director === true` — non-directors don't see the tab, and hitting the endpoint returns 403.

**Verification (iter34)**
- 17/17 pytest PASS. Ledger extract behavior IS bit-identical to pre-refactor (same shapes, same status codes, same 7-row insert pattern on entry-fee collect, same ace-pool increment).
- Compliance logic verified: 3 scorecards / 0 → 1 → 3 `player_certified` flips → `can_sweep_finalize` false / false / true, `pending_certification` length 3 → 2 → 0.
- iter33 regression still 13/13 PASS.
- Frontend verified: director sees "Compliance" tab, non-director does not, all data-testids present (compliance-tab, compliance-clubhouse-card, compliance-outstanding-{id}, compliance-round-{id}, compliance-pending-{scId}, compliance-agreed-pct).

**Known follow-ups (called out by testing agent code review)**
- `player_certified` isn't yet writable via any public endpoint — only `finalized` and (future) `certified_by_director` are. Until a "player certifies own card" endpoint exists, the compliance board treats scorecards as pending unless the director/finalize path has flipped them. **Backlog: add `POST /scorecards/{id}/certify` for player self-certification.**
- Ledger CSV token via `?auth=` works but consider signed short-lived tokens before public launch.
- Compliance rounds not paginated (limit 200) — fine at current scale.
- Rounds refactor still deferred to Session 44 (20+ endpoints + WebSocket manager — high risk, needs its own iteration).

## Prioritized backlog (post-Session-43)
- **P0** — Deploy Sessions 40/41/42/43 to prod once user OKs the beta email preview.
- **P0** — User to submit `upload_certificate.pem` + upload `acechasers-net-v1.0.3.aab` to Play Console.
- **P1** — After Play reset lands, admin presses "Resend to ALL".
- **P1** — Player self-certification endpoint (`POST /scorecards/{id}/certify`) — closes the compliance loop.
- **P1** — Extract Rounds + Scorecards from `leagues_router.py` (phase 3 refactor, ~20 endpoints + WebSocket).
- **P1** — Invite-friend referral flow.
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Signed short-lived tokens for CSV downloads.
- **P2** — Sentry (needs user DSN).
- **P2** — Bulk-email audit log.
- **P2** — Atomic founding-member counter for high-concurrency signups.
- **P2** — Introduce `routers/_shared.py` to hold `api_router`, `db`, common deps — future-proof the tail-import chain.
- **P3** — Real-time notifications for non-round events.


### Session 44 — Player self-certify + Rounds side-router extract + Compliance DM nudges (Feb 2026)

**User asks (all three shipped):**
- Player self-certification endpoint so the sweep-finalize loop closes on its own.
- Phase 3 rounds extraction out of the 1,795-line `leagues_router.py`.
- One-tap "DM this player" button on every pending compliance chip.

**Player self-certify (new)**
- `POST /api/scorecards/{scorecard_id}/certify` — flips `player_certified: true` on the caller's OWN scorecard.
- Rules: auth required · caller must be a league member · caller must own the scorecard (403 if not) · idempotent on re-hit (no duplicate ProofLog) · rejects unknown scorecard with 404.
- Writes a ProofLog audit row with `edited_by_name = "<display-name-or-email> · PLAYER-CERTIFIED"` and a WebSocket broadcast (`type: score_update, player_certified: true`) so the round page updates live.
- Frontend `pages/leagues/RoundScorecard.jsx`:
  - New "Certify My Card" button on the owner's row only, hidden once already certified or finalized. Disabled during POST in-flight.
  - New "You OK'd" badge appears post-certification (until director finalizes).
  - Tooltip: "Approve my own scorecard so the director can finalize the round."

**Rounds side-router extract (scoped phase 3)**
- New `backend/routers/leagues_rounds_router.py` — moves 6 self-contained "side data" endpoints:
  - `POST/GET /rounds/{id}/chat`
  - `PATCH /rounds/{id}/director-notes`
  - `POST/GET /rounds/{id}/ctp`
  - `DELETE /ctp/{entry_id}`
- Same tail-import pattern used by clubhouse/ledger/compliance — endpoints attach to the shared `api_router`, imports helpers/models from `leagues_router`.
- **leagues_router.py: 1,795 → 1,647 lines** (148-line reduction). Score/finalize/WebSocket/payout/sweep intentionally stay in `leagues_router.py` — those are phase 4 (higher risk, own session).
- Route-registry regression test confirms zero double-mounts.

**Compliance DM nudges**
- `leagues_compliance_router.py` — `outstanding_members[]` and `pending_certification[]` rows now include `user_id` (nullable for manually-added members without a linked account).
- `components/ComplianceTab.jsx` — every clubhouse-outstanding chip and every scorecard-pending chip is now a button. Click → `navigate("/messages", { state: { withUid, withName } })` which the existing Messages deep-link consumes. When `user_id` is null the button renders disabled with a toast fallback ("This player doesn't have a linked account yet — can't DM.").
- Adds a subtle `ChatCircleDots` icon on each button so the affordance is visible without cluttering the layout.

**Verification (iter35)**
- **39/39 pytest PASS** (22 new + 17 iter34 regression).
- Self-certify covers auth/ownership/idempotency; compliance dashboard reflects certifications instantly; rounds-router extraction bit-identical to pre-move behaviour.
- Applied one minor code-review polish: `edited_by_name` now falls back to `email` then `user_id` if Firebase display name is empty, so audit logs never render " · PLAYER-CERTIFIED" with a blank leading name.

## Prioritized backlog (post-Session-44)
- **P0** — Deploy Sessions 40/41/42/43/44 to prod once user OKs the beta email preview.
- **P0** — User to submit `upload_certificate.pem` + upload `acechasers-net-v1.0.3.aab` to Play Console.
- **P1** — After Play reset lands, admin presses "Resend to ALL".
- **P1** — Rounds extraction phase 4 (score/finalize/sweep/payout/WebSocket) — leagues_router.py can drop under 800 lines when this lands. Higher risk; own session.
- **P1** — Invite-friend referral flow.
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Signed short-lived tokens for CSV downloads.
- **P2** — Introduce `routers/_shared.py` to house `api_router`, `db`, common deps.
- **P2** — Sentry (needs user DSN).
- **P2** — Bulk-email audit log.
- **P2** — Atomic founding-member counter for high-concurrency signups.
- **P3** — Real-time notifications for non-round events.


### Session 45 — UDisc-style green-themed ScorecardGrid + production sign-in triage (Feb 2026)

**User asks:**
- Redesign the scorecard component as a UDisc-style tabular grid with the Ace Chasers green brand palette.
- Sign-in issues reported by multiple users on production (Cloudflare "couldn't parse origin response") — both email/password AND Google sign-in.

**ScorecardGrid (new)**
- New `frontend/src/components/ScorecardGrid.jsx` — pure display component (no scoring inputs).
- Header block:
  - Disc-icon avatar in an emerald-900 pill + `Ace Chasers` monogram in emerald-700 letter-spacing.
  - Course/round name in `text-emerald-950` (`font-display`, xl→2xl).
  - Location under it in `text-slate-500`.
  - Soft `bg-emerald-100 text-emerald-800` chip for the league name; `text-slate-600` game-type ("Singles" / "Doubles" derived from `league.format`); optional date.
  - Player-names strip under the header.
- 4-row responsive table (`<table>` w/ colgroup + sticky first + last column):
  - Row 1: hole numbers — `bg-green-50/50 text-emerald-900 border-emerald-100`.
  - Row 2: par per hole — mono tabular-nums cells.
  - Row 3: optional distances if `round.distances_per_hole` is provided.
  - Rows 4+: one per scorecard with color-coded score cells (see below).
  - Sticky "TOTAL" column on the right in solid `bg-emerald-800 text-white` per spec.
- Score cell coloring (disc-golf convention):
  - Eagle-or-better → `bg-blue-800 text-white`.
  - Birdie → `bg-green-500 text-white`.
  - Par → `bg-emerald-50/60 text-slate-800`.
  - Bogey → `bg-orange-100 text-orange-900`.
  - Double+ Bogey → `bg-red-700 text-white`.
- Legend footer explains the palette.
- Horizontal scroll on narrow viewports keeps the mobile experience readable without breaking the sticky columns.
- Includes rich data-testids: `scorecard-grid`, `scorecard-grid-course`, `scorecard-grid-location`, `scorecard-grid-league-tag`, `scorecard-grid-game-type`, `scorecard-grid-players`, `grid-hole-N`, `grid-par-N`, `grid-dist-N`, `grid-scorecard-row-{scId}`, `grid-score-{scId}-{holeN}`, `grid-total-{scId}`.
- Wired into `pages/leagues/RoundScorecard.jsx` via a new **Score / Scorecard toggle** (`scorecard-view-score` + `scorecard-view-grid` testids). Score = current hole-by-hole scoring UI (unchanged). Scorecard = the new UDisc grid. Existing scoring/finalize/self-certify flow untouched.

**Production sign-in triage**
- Symptom: multiple users report Cloudflare "couldn't parse origin response" during email/password AND Google sign-in on acechasers.net.
- Preview `/api/auth/sync` verified healthy: correct 401 JSON with `Missing Bearer token` on unauth and `Firebase token verification failed:...` on bad token. No empty responses, no 500s, correct Content-Type.
- Root-cause list to check on the deployed environment:
  1. `FIREBASE_SERVICE_ACCOUNT_JSON` env var must be set on production. If missing, Firebase Admin fails to init and `verify_token` can raise unexpectedly.
  2. Mongo latency/timeout on production — the sync endpoint does a `count_documents` + `update_one` + `find_one`. If Atlas is throttling or the connection string is stale, the request hangs past Cloudflare's origin timeout (100s default).
  3. Response headers: FastAPI + StreamingResponse chains normally close cleanly, but if there is any middleware writing partial bytes and then raising, Cloudflare sees a malformed HTTP response.
  4. Prod is currently on the Session 39-era code (user hasn't deployed 40–45 yet). The auth_sync in that build did NOT have the `_is_test_email` short-circuit — behavior fine, but if there was a Firebase init or env issue it would be latent.
- Recommended fix path: **redeploy the current preview**. Session 44's auth changes have defensive try/except around token verify + user email is optional + return-shape is always ProfileOut, so any of the above latent issues surface as clean 401/500 JSON instead of an empty response Cloudflare can't parse. If after redeploy the issue persists, escalate to Emergent Support with the specific request-id from Cloudflare's error page since only they can see the origin logs on the deployed environment.

## Prioritized backlog (post-Session-45)
- **P0** — Deploy Sessions 40–45 to prod (unblocks the sign-in issue AND ships all the new features).
- **P0** — After deploy, verify sign-in on acechasers.net. If still broken, contact Emergent Support with a request-id from Cloudflare's 520/522 error page.
- **P0** — User to submit `upload_certificate.pem` + upload `acechasers-net-v1.0.3.aab` to Play Console.
- **P1** — After Play reset lands, admin presses "Resend to ALL".
- **P1** — Rounds extraction phase 4 (score/finalize/sweep/payout/WebSocket).
- **P1** — Invite-friend referral flow.
- **P1** — DM Fair Play gate for reply flows.
- **P2** — Signed short-lived tokens for CSV downloads.
- **P2** — Introduce `routers/_shared.py`.
- **P2** — Sentry (needs user DSN).
- **P2** — Bulk-email audit log.
- **P2** — Atomic founding-member counter.
- **P2** — Print / PDF export of the ScorecardGrid so directors can post a physical copy at the course.
- **P3** — Real-time notifications for non-round events.


### Session 46 — Print / PDF export of Scorecard + Deploy trigger (Feb 2026)

**User asks:**
- One-tap PDF export of the ScorecardGrid so directors can pin a physical copy at the course.
- Deploy Sessions 40-45 to production (they suspect it will fix the sign-in Cloudflare error).

**Print / PDF export (new)**
- Zero-dependency approach — uses the browser's native Print dialog which every OS exposes a "Save as PDF" option in.
- `frontend/src/index.css` — new `@media print` block scoped to `body[data-print-target="scorecard-grid"]`:
  - Hides everything on the page.
  - Un-hides only the ScorecardGrid card (`[data-testid="scorecard-grid"]`).
  - Forces exact color reproduction (`-webkit-print-color-adjust: exact`) so the emerald palette + score-cell colors survive on paper.
  - Hides the view toggle + Print button itself (they'd be visual noise on the printed sheet).
- `@page { size: landscape; margin: 0.4in }` — most scorecards fit on a landscape letter/A4.
- `pages/leagues/RoundScorecard.jsx`:
  - New "Print / PDF" button appears next to the Score/Scorecard toggle when in Scorecard view.
  - `handlePrintScorecard()` sets the `data-print-target` attribute, calls `window.print()` in the next paint cycle, and cleans up on `afterprint` (5s timeout fallback for Safari).
  - Button data-testid: `scorecard-print-btn`.

**Deploy trigger (Sessions 40-45)**
- Dispatched to `emergent__send_to_deployer` with intent="deploy". Job `db4a0c76-ad6d-4f1b-bea5-0c419a46e0eb`.
- Bundle shipped: Google Group beta emails + Resend-to-All + First Run founding tier + League Dashboard refactor + card-create UX fix + Founding recount to 40 excluding QA emails + `/leagues/{id}/dashboard` bundle + Ledger/Compliance/Rounds side sub-router extractions + `POST /scorecards/{id}/certify` + Compliance DM nudges + UDisc ScorecardGrid + Print/PDF export.
- **39/39 pytest** across iters 31→35.

**Post-deploy verification checklist (user's action after Emergent finishes):**
1. Open acechasers.net and sign in — the Cloudflare "couldn't parse response" issue should be gone (Session 44 hardened Firebase token verify).
2. If it's NOT gone, take a **request-id from the Cloudflare error page** and paste it here; only Emergent Support can read origin logs on the deployed environment.
3. Open `/beta-admin` and press "Resend to ALL" so the new Google Group copy hits your entire user base.
4. Verify a league page loads the new dashboard bundle (Network tab: single `/dashboard` call instead of 4).
5. Try the Print / PDF button on a scorecard.

