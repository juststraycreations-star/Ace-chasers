// PWA service worker registration.
//
// Runs after the app has finished loading so it never blocks first paint.
// Silently no-ops on browsers without SW support (older Safari, etc.).
//
// Feb 2026: added a self-healing path — when the app boots we ask the
// active SW to purge its caches (if it's on an outdated version). This
// rescues users whose old v1 service worker was left in a wedged state
// after the Cloudflare 520 sign-in bug and would otherwise need a
// manual hard-refresh.
export function registerServiceWorker() {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;
  // Skip registration during Vite dev — the dev server serves files with
  // headers that confuse the SW and cause noisy console errors.
  if (import.meta.env?.DEV) return;

  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });

      // Ask the active worker to blow away every cache. Safe because
      // our SW ignores messages it doesn't recognise, and the message
      // handler in v2+ handles {type:'CLEAR_CACHES'} idempotently.
      // Old wedged v1 workers just ignore this — but the next line
      // triggers an update check that swaps them out for v2 on the
      // very next navigation.
      try { reg.active?.postMessage({ type: 'CLEAR_CACHES' }); } catch { /* non-fatal */ }
      try { await reg.update(); } catch { /* non-fatal */ }

      // If a new worker takes control mid-session, reload once so the
      // page and its scripts come from the new revision instead of the
      // wedged old one that was serving stale cached shell HTML.
      let didReload = false;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (didReload) return;
        didReload = true;
        window.location.reload();
      });
    } catch (err) {
      // Non-fatal: the site works fine without offline caching.
      console.warn('Service worker registration failed:', err);
    }
  });
}
