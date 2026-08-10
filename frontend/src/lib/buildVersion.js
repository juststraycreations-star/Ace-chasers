// Auto cache-bust on deploy.
//
// The app is baked with `__ACE_BUILD_ID__` at Vite build time (Vercel,
// Netlify, our custom pipeline — anywhere we set `ACE_BUILD_ID` before
// `vite build`). At runtime we poll `/api/version` and compare. When the
// server reports a different build id than the one baked into this
// bundle, the user is holding a stale bundle → we surface a subtle
// "New version" toast with a Reload button, and clear the service
// worker + cache storage on click so the next paint comes from the
// fresh bundle.
//
// In `vite dev`, `__ACE_BUILD_ID__` is the literal string `"dev"` and
// we short-circuit — dev has hot reload and doesn't need this.
import { toast } from "sonner";
import { api } from "@/lib/api";

// eslint-disable-next-line no-undef
const CLIENT_BUILD_ID = typeof __ACE_BUILD_ID__ !== "undefined" ? __ACE_BUILD_ID__ : "dev";

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 min
let promptShown = false;

async function fetchServerBuildId() {
  try {
    const { data } = await api.get("/version");
    return data?.build_id || null;
  } catch {
    return null;
  }
}

async function hardReload() {
  // Best-effort: unregister every service worker registered for this
  // origin, then delete every Cache Storage entry. Both APIs are
  // wrapped in try/catch — none of them are strictly required for the
  // reload to fix the stale bundle (the query-string cache-bust below
  // does that on its own) but they help old Safari + Cloudflare edges.
  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
  } catch { /* ignore */ }
  try {
    if (typeof caches !== "undefined") {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch { /* ignore */ }
  const u = new URL(window.location.href);
  u.searchParams.set("v", Date.now().toString(36));
  window.location.replace(u.toString());
}

function promptReload() {
  if (promptShown) return;
  promptShown = true;
  toast("New version available", {
    description: "The site was just updated. Reload to get the latest.",
    duration: Infinity,
    action: {
      label: "Reload",
      onClick: () => hardReload(),
    },
    // Keep the toast dismissible so a user in the middle of a scorecard
    // can defer, and open it again on the next check-in.
    onDismiss: () => { promptShown = false; },
    id: "ace-build-mismatch",
  });
}

async function checkNow() {
  if (CLIENT_BUILD_ID === "dev") return;
  const serverId = await fetchServerBuildId();
  if (!serverId || serverId === "dev") return;
  if (serverId !== CLIENT_BUILD_ID) promptReload();
}

/**
 * startBuildVersionWatcher — mount once at app boot (App.jsx). Runs an
 * initial check after 20s (avoid racing first paint), then every 5 min
 * and on window focus. Idempotent — a second call is a no-op.
 */
let started = false;
export function startBuildVersionWatcher() {
  if (started) return;
  started = true;
  // First check delayed so we don't race the first paint / auth handshake.
  setTimeout(checkNow, 20_000);
  // Periodic poll.
  setInterval(checkNow, POLL_INTERVAL_MS);
  // Refocus check — catches users who tab away for a day and come back.
  if (typeof window !== "undefined") {
    window.addEventListener("focus", checkNow);
    window.addEventListener("online", checkNow);
  }
}

export const __TEST__ = { CLIENT_BUILD_ID, checkNow, hardReload };
