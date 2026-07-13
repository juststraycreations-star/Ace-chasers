// PWA service worker registration.
//
// Runs after the app has finished loading so it never blocks first paint.
// Silently no-ops on browsers without SW support (older Safari, etc.).
export function registerServiceWorker() {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;
  // Skip registration during Vite dev — the dev server serves files with
  // headers that confuse the SW and cause noisy console errors.
  if (import.meta.env?.DEV) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js', { scope: '/' })
      .catch((err) => {
        // Non-fatal: the site works fine without offline caching.
        console.warn('Service worker registration failed:', err);
      });
  });
}
