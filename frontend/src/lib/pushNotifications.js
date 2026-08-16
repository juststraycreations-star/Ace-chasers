/**
 * pushNotifications.js — Ace Chasers push registration bridge.
 *
 * Design summary
 * ──────────────
 *   • Wraps `@capacitor/push-notifications` so the same code compiles
 *     into the web bundle without breaking on plain browsers. When
 *     running in a browser the module short-circuits to a `web`
 *     no-op that never touches the native bridge.
 *   • On Android 13+ (API 33) the OS gates notifications behind an
 *     explicit runtime `POST_NOTIFICATIONS` permission. Capacitor
 *     handles the underlying API level check for us — we just call
 *     `PushNotifications.requestPermissions()` and it does the right
 *     thing on every supported OS version.
 *   • The primer modal (see `PushPermissionPrimer.jsx`) fires BEFORE
 *     the native system dialog. A user who taps "Not now" on the
 *     primer never sees the OS dialog, so the OS's "deny" quota
 *     stays intact for a future prompt.
 *   • On successful registration we POST { token, platform } to
 *     /api/push/register-token. The backend upserts on `token`, so
 *     re-registers on cold-start don't create duplicate rows.
 */

let isNativePlatform = null;

async function detectNative() {
  if (isNativePlatform !== null) return isNativePlatform;
  try {
    // Dynamic import so pure-web bundles never load Capacitor's core.
    const { Capacitor } = await import("@capacitor/core");
    isNativePlatform = Capacitor.isNativePlatform();
    return isNativePlatform;
  } catch {
    isNativePlatform = false;
    return false;
  }
}

async function getPlatform() {
  try {
    const { Capacitor } = await import("@capacitor/core");
    return Capacitor.getPlatform(); // "android" | "ios" | "web"
  } catch {
    return "web";
  }
}

/**
 * Check whether notification permission has already been granted.
 * Safe to call on every route change — no dialog is shown.
 */
export async function getNotificationPermissionState() {
  if (!(await detectNative())) return "web-unsupported";
  const { PushNotifications } = await import("@capacitor/push-notifications");
  const { receive } = await PushNotifications.checkPermissions();
  return receive; // "granted" | "denied" | "prompt" | "prompt-with-rationale"
}

/**
 * requestNotificationPermission — the full Android 13+ opt-in flow.
 *
 * The caller MUST have already shown the primer UI and gotten the
 * user's positive response — see PushPermissionPrimer.jsx. This
 * function assumes the user just tapped "Allow" on the primer.
 *
 * @param {Object} opts
 * @param {string} opts.playerId    - Ace Chasers user id (from /auth/sync).
 * @param {Function} [opts.postToken] - async (payload) => api.post ...
 *                                    Kept as a param so tests / storybooks
 *                                    can inject a mock without importing api.
 * @returns {Promise<{state: string, token?: string}>}
 */
export async function requestNotificationPermission({ playerId, postToken } = {}) {
  if (!(await detectNative())) {
    return { state: "web-unsupported" };
  }

  const { PushNotifications } = await import("@capacitor/push-notifications");

  // 1. Runtime permission — Capacitor bridges this to the correct
  //    Android 13+ POST_NOTIFICATIONS system dialog under the hood.
  const perm = await PushNotifications.requestPermissions();
  if (perm.receive !== "granted") {
    return { state: perm.receive || "denied" };
  }

  // 2. Register with FCM (Android) / APNs (iOS). The native side
  //    fires `registration` when the token is minted or refreshed.
  //    Because Capacitor listeners persist for the lifetime of the
  //    app, we set up the handler BEFORE calling register().
  const platform = await getPlatform();

  const token = await new Promise((resolve, reject) => {
    let settled = false;
    const done = (fn, v) => {
      if (settled) return;
      settled = true;
      fn(v);
    };
    // Guard against a lost callback — if the native bridge is slow or
    // silently fails we still resolve after 15s so the UI can move on.
    const safety = setTimeout(() => done(reject, new Error("Push registration timed out")), 15_000);

    PushNotifications.addListener("registration", (evt) => {
      clearTimeout(safety);
      done(resolve, evt.value);
    });
    PushNotifications.addListener("registrationError", (err) => {
      clearTimeout(safety);
      done(reject, new Error(err?.error || "registrationError"));
    });

    PushNotifications.register();
  });

  // 3. Log the token so a manager copying it out of the debug console
  //    can drop it into an FCM test send.
  // eslint-disable-next-line no-console
  console.info("[push] token minted", token);

  // 4. Send to backend for fan-out.
  if (typeof postToken === "function") {
    try {
      await postToken({ playerId, token, platform });
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("[push] register-token POST failed", e);
    }
  }

  return { state: "granted", token, platform };
}
