# Ace Chasers — Test credentials

## Dev / preview environment
The app currently runs in **dev mode** because no Firebase service account / web SDK keys have been supplied yet. Authentication still works end-to-end via the dev fallback (`src/lib/devAuth.js` mints an unsigned JWT that the backend's dev path decodes without verification).

### How to log in
Pick any email + password on the Login page (or use the Sign-Up form). Each unique email becomes a distinct user in Mongo. Example:
- email: `tester@example.com`
- password: `demo1234`

### Switching to real Firebase
1. Create a Firebase project at <https://console.firebase.google.com>.
2. **Enable** in the console: Authentication → Sign-in method → enable both **Email/Password** and **Google**.
3. Project settings → Your apps → Web → copy the config. Paste into `/app/frontend/.env`:
   - `REACT_APP_FIREBASE_API_KEY`
   - `REACT_APP_FIREBASE_AUTH_DOMAIN`
   - `REACT_APP_FIREBASE_PROJECT_ID`
   - `REACT_APP_FIREBASE_STORAGE_BUCKET`
   - `REACT_APP_FIREBASE_MESSAGING_SENDER_ID`
   - `REACT_APP_FIREBASE_APP_ID`
4. Project settings → Service accounts → Generate new private key. Save as `/app/backend/firebase-admin.json` and set in `/app/backend/.env`:
   - `FIREBASE_SERVICE_ACCOUNT_JSON=/app/backend/firebase-admin.json`
   - `FIREBASE_PROJECT_ID=<your-project-id>`
5. Restart services: `sudo supervisorctl restart frontend backend`.

After step 5 the dev fallbacks self-disable; tokens are then fully verified server-side.

## Seeded demo users
The backend automatically seeds 3 demo players on startup. Two of them (`seed-sarah`, `seed-amanda`) auto-like every new signup so the matched-likes / "Add Friend" flow can be demoed without two human accounts.

| uid           | name    | auto-likes you? |
|---------------|---------|-----------------|
| seed-sarah    | Sarah   | ✅ yes (mutual) |
| seed-jessica  | Jessica | ❌ no            |
| seed-amanda   | Amanda  | ✅ yes (mutual) |
