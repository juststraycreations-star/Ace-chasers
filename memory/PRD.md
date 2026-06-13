# Ace Chasers — PRD

## Original problem statement
> Its a website it needs the profile preview to be what is seen as the public profile it should have the non-private data displayed exactly as it is now on the preview public profile need to add the element favorite frisbee option to the profile page when someone likes a profile they should go to a like page that will be in a separate tab.

## App overview
Ace Chasers is a disc-golf-themed dating / partner-matching web app (React + Vite + Zustand + Tailwind). Users sign in, swipe through other players on the Discovery feed, message matches, and curate their own profile.

## Architecture
- Frontend: React 18 + Vite 5, Tailwind CSS, Zustand (with `persist` middleware → localStorage), React Router v6.
- Backend: Minimal FastAPI stub at `/app/backend/server.py` (only `/api/health`). All app data is currently mocked client-side.
- Folders: `/app/frontend` (UI), `/app/backend` (stub), `/app/frontend/src/data/mockPlayers.js` (shared mock deck).

## Core requirements (static)
1. Profile **preview** mode must visually match the **public profile** (PlayerCard) layout.
2. Profile must include a **Favorite Frisbee** free-text field (public, no privacy toggle).
3. A new **Likes** tab in the main navigation listing every profile the user has liked. Mutual likes surface an **Add Friend** call-to-action.

## What's been implemented (Jan 2026)
- Restructured project from `/app` root into `/app/frontend` + `/app/backend` to align with supervisor.
- Added Vite config, dev server on `0.0.0.0:3000`, stub backend on `:8001`.
- `profileStore` (was missing — Profile.jsx referenced it but file didn't exist) with localStorage persistence.
- `authStore` extended with `updateUser` and localStorage persistence.
- `matchStore` rewritten to persist `likedPlayers` / `passedPlayers` as `{ player, likedAt, matched, friended }` records. Added `addFriend` and `removeLike` actions and demo mutual-match IDs.
- `Profile.jsx` split into edit-mode and view-mode; view-mode now renders `PublicProfilePreview` which mirrors `PlayerCard` styling exactly. Added Favorite Frisbee input.
- `PlayerCard.jsx` updated to surface Favorite Frisbee and pass the full player object on like/pass.
- `Discovery.jsx` rebuilt around the persisted match store; deck filters out previously-swiped players.
- New `Likes.jsx` page (`/likes` route) with match badges, Add Friend link, Unlike action, empty state.
- `Navigation.jsx` & `App.jsx` updated to add the Likes tab and route.
- Mock player data centralized in `src/data/mockPlayers.js` and includes `favoriteFrisbee` for each player.

## Data-testids added
`profile-view`, `profile-edit-view`, `profile-edit-btn`, `profile-cancel-btn`, `profile-save-btn`, `profile-favorite-frisbee-input`, `public-profile-preview`, `public-profile-favorite-frisbee`, `nav-likes`, `nav-discovery`, `nav-profile`, `nav-messages`, `nav-logout`, `like-btn`, `pass-btn`, `liked-player-{id}`, `match-badge-{id}`, `add-friend-link-{id}`, `friended-label-{id}`, `unlike-btn-{id}`, `likes-view`, `likes-empty`, `discovery-view`, `discovery-empty`.

## Backlog / next steps
- P1: Wire `Likes` and `Matches` to a real backend (currently demo-only; IDs 1 & 3 are hard-coded as mutual).
- P1: Persist Favorite Frisbee server-side once Firebase / API is connected.
- P2: Replace mock conversations in `Messages.jsx` with the same persisted store pattern so chats survive refresh.
- P2: Auth: replace mock login/signup with the Firebase config already scaffolded (or Emergent-managed Google auth).
- P3: "Open Likes in a new browser tab" — currently a separate in-app route; expose `target="_blank"` from a deep-link if requested.
