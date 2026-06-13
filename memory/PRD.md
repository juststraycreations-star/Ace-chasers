# Ace Chasers — PRD

## Original problem statement (initial)
> Its a website it needs the profile preview to be what is seen as the public profile it should have the non-private data displayed exactly as it is now on the preview public profile need to add the element favorite frisbee option to the profile page when someone likes a profile they should go to a like page that will be in a separate tab.

## Follow-up requests
1. Replace mock login/signup with **real Firebase Authentication** (Email/Password + Google).
2. Wire Likes / Matches to a **real backend** (FastAPI + MongoDB). Seed the existing mock players as real DB users.

## App overview
Ace Chasers is a disc-golf-themed swipe-to-match web app. Users sign in, swipe through other players (Discovery), match on mutual likes, view their likes/matches, and manage their public profile.

## Architecture
- **Frontend**: React 18 + Vite 5, Tailwind, Zustand, React Router v6, firebase v10 web SDK, axios.
- **Backend**: FastAPI + Motor (Mongo async). Firebase Admin SDK for ID-token verification.
- **DB**: MongoDB collections — `users` (uid, email, profile fields), `swipes` (from_uid + to_uid + action), `matches` (canonical user_a < user_b ordering + friended_by[]).
- **Auth flow**: Frontend signs the user in via Firebase, attaches `Authorization: Bearer <idToken>` on every API call, backend `get_current_user` dependency verifies and resolves `uid`. Dev fallback (unsigned JWT) when Firebase env vars are not yet configured.

## Core requirements (static)
1. Profile **preview** mode must visually match the **public profile** (PlayerCard layout).
2. Profile must include a **Favorite Frisbee** free-text field.
3. A **Likes** tab in the main nav listing every profile the user has liked. Mutual likes surface "It's a match!" + "+ Add friend".
4. **Real auth** with Firebase (Email/Password + Google).
5. **Real backend** for users/discovery/likes/matches with seeded demo players.

## What's been implemented (Jan 2026)
### Session 1 (polish)
- Restructured `/app` → `/app/frontend` + `/app/backend` (Vite + stub FastAPI).
- Added missing `profileStore`, `updateUser` in authStore, persisted match/profile/auth stores.
- New `PublicProfilePreview` component — Profile page view-mode mirrors PlayerCard.
- Added `favoriteFrisbee` free-text field across Profile, PlayerCard, Discovery, Likes.
- New `Likes` tab + route with match badge + Add Friend / Unlike actions.

### Session 2 (real auth + real backend)
- **Backend** (`/app/backend`):
  - `firebase_auth.py` — graceful init of firebase-admin; verifies ID tokens when `FIREBASE_SERVICE_ACCOUNT_JSON` set, else decodes unverified (dev mode, logged warning).
  - `db.py` — Mongo singleton + `ensure_indexes` + `seed_demo_users` (Sarah/Jessica/Amanda; Sarah & Amanda auto-like every new signup).
  - `server.py` — endpoints:
    - `POST /api/auth/sync` — upsert user + ensure inbound demo likes.
    - `GET/PUT /api/users/me`.
    - `GET /api/discovery` — players excluding self + previously-swiped.
    - `POST /api/swipes` — records swipe, creates Match on mutual like.
    - `GET /api/likes` — lists liked players with `matched` + `friended` flags.
    - `POST /api/matches/{uid}/friend` — adds caller to `friended_by`.
    - `DELETE /api/likes/{uid}` — removes like and any related match.
- **Frontend**:
  - `lib/firebase.js` — modular SDK init (Email/Password + Google provider).
  - `lib/api.js` — axios with auto-attached bearer token (Firebase idToken or dev token).
  - `lib/devAuth.js` — dev fallback session (unsigned JWT) when Firebase keys not set.
  - `components/AuthProvider.jsx` — `onAuthStateChanged` listener that hydrates authStore + calls `/api/auth/sync`.
  - `pages/Login.jsx` + `pages/SignUp.jsx` — full Firebase flows + Google button; dev fallback path.
  - `store/authStore.js` rewritten: holds Firebase user + API-loaded profile + `authReady` gate.
  - `store/matchStore.js` rewritten: API-backed (`fetchDeck`, `fetchLikes`, `swipe`, `addFriend`, `removeLike`).
  - `pages/Discovery.jsx`, `pages/Likes.jsx`, `pages/Profile.jsx` updated to consume the API.
  - `App.jsx` waits for `authReady` before routing.
- Dependencies added: backend → `firebase-admin`, `motor`, `pymongo`, `pydantic-settings`, `python-dotenv`, `pyjwt`. Frontend → `firebase`, `axios`.

## API surface
All routes prefixed with `/api`, all protected (except `/api/health`):
- `GET  /api/health`
- `POST /api/auth/sync`
- `GET  /api/users/me`
- `PUT  /api/users/me`
- `GET  /api/discovery`
- `POST /api/swipes` (body: `{target_uid, action: "like"|"pass"}`)
- `GET  /api/likes`
- `POST /api/matches/{target_uid}/friend`
- `DELETE /api/likes/{target_uid}`

## Verified flows (Playwright)
1. Signup → backend creates user → discovery deck has 3 seeded players.
2. Like Sarah → backend detects Sarah's pre-seeded like → Match row created.
3. Like Jessica → no inbound like → not matched.
4. Like Amanda → mutual → Match row created.
5. Likes page → shows 3 likes, 2 matches, with "It's a match!" badges + Add Friend links.
6. Click "+ Add friend" on Sarah → `friended_by` array contains caller uid → UI flips to "✓ Friend added".
7. Profile edit → save Favorite Frisbee → persisted via PUT /users/me, reflected in preview.
8. DB sanity: 4 users, 5 swipes, 2 matches with correct friended_by.

## Backlog / next steps
- P0: User pastes Firebase web config + service account JSON to switch off dev mode (instructions in `/app/memory/test_credentials.md`).
- P1: Profile picture uploads (current Firebase storage scaffold in `src/config/firebase.js` uses a hand-rolled REST flow; swap to Firebase Storage SDK once auth is live).
- P1: Wire Messages page to a real conversations/messages backend.
- P2: Add unmatch + report/block actions.
- P3: Real-time match notifications via Firestore listener or websockets.
