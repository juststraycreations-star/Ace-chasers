import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRinging, X } from "@phosphor-icons/react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import {
  getNotificationPermissionState,
  requestNotificationPermission,
} from "@/lib/pushNotifications";

const SEEN_KEY = "ace-chasers.push.primer.seen";

/**
 * PushPermissionPrimer — one-time modal that appears just before the
 * Android runtime `POST_NOTIFICATIONS` system dialog. Two goals:
 *
 *   1. Educate the user on *why* we're asking, which measurably lifts
 *      opt-in rates over the raw OS prompt.
 *   2. Give them a "Not now" out that does NOT consume the OS's
 *      deny quota (system dialog is only fired if they tap Enable).
 *
 * Behaviour
 * ─────────
 *   • On mount, checks Capacitor + current permission state. If we're
 *     already granted OR denied, OR the user tapped "Not now"
 *     previously (localStorage `SEEN_KEY`), the primer stays hidden.
 *   • Only fires on native builds (`Capacitor.isNativePlatform()`).
 *     Plain browsers never see it.
 *   • On Enable → calls `requestNotificationPermission` which triggers
 *     the OS dialog, then registers with FCM and POSTs the token to
 *     `/api/push/register-token`.
 */
export default function PushPermissionPrimer() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const profile = useAuthStore((s) => s.profile);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (typeof window === "undefined") return;
      if (window.localStorage?.getItem(SEEN_KEY) === "1") return;
      const state = await getNotificationPermissionState();
      // Only prompt if the platform actually supports a permission
      // dialog AND the user hasn't already been through it.
      if (cancelled) return;
      if (state === "prompt" || state === "prompt-with-rationale") {
        setOpen(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const dismiss = () => {
    // Persist so we don't re-nag on every launch. A user who wants
    // notifications later can flip them from OS settings; a future
    // "Notifications" screen in Settings can also `.removeItem(SEEN_KEY)`
    // to re-trigger the primer.
    try { window.localStorage?.setItem(SEEN_KEY, "1"); } catch { /* quota */ }
    setOpen(false);
  };

  const enable = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await requestNotificationPermission({
        playerId: profile?.user_id || profile?.uid,
        postToken: (payload) => api.post("/push/register-token", payload),
      });
      if (res.state === "granted") {
        toast.success("Notifications on · you're set for live updates", {
          position: "top-center",
        });
      } else if (res.state === "denied") {
        toast.warning("Notifications blocked — you can re-enable from device settings");
      } else {
        toast.info("Notifications aren't available on this device");
      }
    } catch (e) {
      toast.error(e?.message || "Could not enable notifications");
    } finally {
      dismiss();
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
      data-testid="push-permission-primer"
      onClick={busy ? undefined : dismiss}
      role="dialog"
      aria-modal="true"
      aria-labelledby="push-primer-title"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-2xl border border-gray-100 w-full max-w-md p-6"
      >
        <button
          type="button"
          onClick={dismiss}
          disabled={busy}
          data-testid="push-primer-close-btn"
          aria-label="Dismiss"
          className="absolute top-3 right-3 text-slate-400 hover:text-slate-700 p-1 disabled:opacity-40"
          style={{ position: "relative", float: "right" }}
        >
          <X size={16} weight="bold" />
        </button>
        <div className="flex items-center gap-3 mb-3">
          <div className="w-11 h-11 rounded-full bg-emerald-50 text-emerald-700 flex items-center justify-center">
            <BellRinging size={22} weight="duotone" />
          </div>
          <h2
            id="push-primer-title"
            className="font-display text-xl text-slate-900"
          >
            Turn on live round alerts
          </h2>
        </div>
        <p
          className="text-sm text-slate-700 leading-relaxed mb-5"
          data-testid="push-primer-body"
        >
          Ace Chasers needs your permission to send real-time alerts when
          your scoring card updates, a new hole layout freezes, or when a
          league manager pushes automated payouts.
        </p>
        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-2">
          <button
            type="button"
            onClick={dismiss}
            disabled={busy}
            data-testid="push-primer-decline-btn"
            className="text-sm font-medium text-slate-600 hover:text-slate-900 px-4 py-2 rounded-full transition-colors disabled:opacity-40"
          >
            Not now
          </button>
          <button
            type="button"
            onClick={enable}
            disabled={busy}
            data-testid="push-primer-enable-btn"
            className={`text-sm font-semibold rounded-full px-4 py-2 shadow-sm transition-colors inline-flex items-center justify-center gap-2 min-w-[160px] ${
              busy
                ? "bg-emerald-600 text-white opacity-70 cursor-wait"
                : "bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer"
            }`}
          >
            {busy ? "Enabling…" : "Enable notifications"}
          </button>
        </div>
      </div>
    </div>
  );
}
