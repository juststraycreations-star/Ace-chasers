# Ace Chasers — Test credentials & admin runbook

## Auth modes
| Mode | When it's active | Notes |
|---|---|---|
| **Dev** (default) | `FIREBASE_SERVICE_ACCOUNT_JSON` blank | Tokens decoded without signature verification — convenient for local QA. Banner / verification flow disabled. |
| **Firebase** | `FIREBASE_SERVICE_ACCOUNT_JSON` points to a valid service account JSON | Tokens fully verified by `firebase-admin`. Email-verification banner shown until the user clicks the link. |

## Dev login
Pick any email + password on the Login or Sign-Up page. Each unique email becomes its own user record.

Example: `tester@example.com` / `demo1234`

## Switching to real Firebase
1. Create a Firebase project at <https://console.firebase.google.com>.
2. Authentication → Sign-in method → **enable Email/Password AND Google**.
3. Project settings → Your apps → Web → copy the config into `/app/frontend/.env`:
   - `REACT_APP_FIREBASE_API_KEY`
   - `REACT_APP_FIREBASE_AUTH_DOMAIN`
   - `REACT_APP_FIREBASE_PROJECT_ID`
   - `REACT_APP_FIREBASE_STORAGE_BUCKET`
   - `REACT_APP_FIREBASE_MESSAGING_SENDER_ID`
   - `REACT_APP_FIREBASE_APP_ID`
4. Project settings → Service accounts → Generate new private key. Save as `/app/backend/firebase-admin.json` and set in `/app/backend/.env`:
   - `FIREBASE_SERVICE_ACCOUNT_JSON=/app/backend/firebase-admin.json`
   - `FIREBASE_PROJECT_ID=<your-project-id>`
5. Restart: `sudo supervisorctl restart frontend backend`.

## Invite gating (env toggle)
Set `REQUIRE_INVITE=true` in `/app/backend/.env` (then restart backend) to require an admin-issued invite code on first sign-up.
- **Default**: `REQUIRE_INVITE=false` (open signups).
- Existing users are never re-gated.
- The frontend reads this flag via `GET /api/config` on app load and shows the Invite Code field on Sign-Up accordingly.

### Admin API
All admin endpoints require header `X-Admin-Key: <ADMIN_API_KEY>` (set in `/app/backend/.env`, default `change-me-admin-key`).

Create an invite (optionally locked to an email):
```bash
curl -s -X POST http://localhost:8001/api/admin/invites \
  -H "X-Admin-Key: change-me-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com"}'
```
Response includes a `code` like `ACE-XXXX-XXXX`.

List invites:
```bash
curl -s http://localhost:8001/api/admin/invites -H "X-Admin-Key: change-me-admin-key"
```

Revoke an invite:
```bash
curl -s -X DELETE http://localhost:8001/api/admin/invites/ACE-XXXX-XXXX -H "X-Admin-Key: change-me-admin-key"
```

Invites are **single-use**. If `email` is set, only that address can redeem the code (case-insensitive).

## Email verification (soft gate)
- Active only in Firebase mode.
- After signup, `sendEmailVerification` is fired automatically.
- A yellow banner appears at the top of the app until the user verifies. It includes a `Resend email` button (`data-testid="verify-resend-btn"`).
- Backend keeps `users.email_verified` in sync with each token's claims (refreshed on every `auth/sync` and `users/me` call).

## Seeded demo users
The backend auto-seeds 3 demo players on startup. Two of them auto-like every new signup so the matched-likes / "Add Friend" flow can be demoed without two human accounts.

| uid           | name    | auto-likes you? |
|---------------|---------|-----------------|
| seed-sarah    | Sarah   | ✅ yes (mutual) |
| seed-jessica  | Jessica | ❌ no            |
| seed-amanda   | Amanda  | ✅ yes (mutual) |
