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

## Backlog / next steps
- P0: User pastes Firebase web config + service account JSON to switch off dev mode (instructions in `/app/memory/test_credentials.md`).
- P1: Replace `ADMIN_API_KEY` with Firebase custom claims (`admin: true`) once an admin user exists, so the curl endpoints can be moved behind real OAuth.
- P1: Admin web UI for invites (list / create / revoke) instead of curl.
- P2: Invite analytics (who redeemed, when, conversion rate).
- P2: Wire Messages page to a real conversations API.
- P3: Real-time match notifications (Firestore listener or websockets).
