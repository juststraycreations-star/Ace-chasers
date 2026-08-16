> ## ✅ google-services.json — installed Feb 2026
> The real 39-char FCM Android API key has been written to
> `/app/android/app/google-services.json`
> - Project ID: `acechaser-38c33`
> - Package: `net.acechasers.app`
> - Mobile SDK App ID: `1:388698465312:android:726dae7631da76f3de495f`
>
> Next step on your local machine (this sandbox cannot run it):
> ```
> cd frontend && yarn build && npx cap sync android && npx cap open android
> ```


# Iteration 69 — Push Notifications: Native Build Checklist

This sandbox delivered the **JS + backend** layer of push notifications. The
runtime `POST_NOTIFICATIONS` dialog and the actual FCM handshake happen on
the native Android side, which needs a local Android dev environment. Run
the steps below on your local machine.

## Prerequisites
- Node 20+, Yarn, JDK 17, Android Studio (Giraffe or newer).
- Firebase project with an Android app registered and `google-services.json`
  downloaded.

## 1. Add Capacitor scaffolding (once)

```bash
cd frontend
yarn add @capacitor/cli @capacitor/android
npx cap init "Ace Chasers" "net.acechasers.app" --web-dir=dist
npx cap add android
```

Then copy `google-services.json` into `android/app/`.

## 2. Enable the Push Notifications plugin on Android

Edit `android/app/src/main/AndroidManifest.xml` and confirm the
`POST_NOTIFICATIONS` permission is declared (Android 13+):

```xml
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

`@capacitor/push-notifications` already registers the FCM messaging
service, so no additional Manifest wiring is needed.

## 3. Build + sync

```bash
cd frontend
yarn build
npx cap sync android
npx cap open android
```

Then run on a device / emulator with API 33+ to see the runtime dialog.

## 4. What the JS/backend layer already provides

Already shipped in preview (Iteration 69):

- `src/lib/pushNotifications.js` — `requestNotificationPermission()`,
  `getNotificationPermissionState()`. Guards against pure-web bundles via
  a dynamic `@capacitor/core` import.
- `src/components/PushPermissionPrimer.jsx` — custom modal shown BEFORE
  the OS dialog. Persists a "seen" flag in localStorage so users aren't
  re-nagged on every launch.
- Mounted in `App.jsx` alongside `OnboardingGate`, gated on
  `isAuthenticated`.
- Backend endpoints (`push_router.py`):
  - `POST /api/push/register-token` — upserts on `token`, returns 400 on
    empty/too-short tokens.
  - `GET /api/push/tokens` — actor-scoped listing.
  - `POST /api/push/unregister-token` — idempotent, actor-scoped delete.
- `push_tokens` Mongo collection with unique index on `token` +
  secondary index on `user_id`.
- pytest coverage: 5/5 green (`test_iteration69.py`).

## 5. Testing the full loop on device

1. Sign in in the Capacitor-wrapped app.
2. The Primer modal fires on first launch — tap **Enable notifications**.
3. The OS `POST_NOTIFICATIONS` dialog appears — tap Allow.
4. Watch `adb logcat -s Capacitor:V ace-chasers:V` for the
   `[push] token minted <FCM_TOKEN>` line.
5. Confirm the token landed in Mongo:
   ```
   db.push_tokens.findOne({ user_id: "<your_user_id>" })
   ```
6. Fire a test send from Firebase Console → Cloud Messaging → "Send
   test message" using that token.
