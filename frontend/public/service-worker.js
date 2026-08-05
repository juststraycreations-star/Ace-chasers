// Ace Chasers service worker
// -----------------------------------------------------------------------------
// This exists primarily so the site meets the PWA "installability" bar
// (needed for Google Play submission via PWABuilder / TWA). It also gives
// users a cached shell for the login/landing pages when they're offline.
//
// Strategy:
//   - Precache the app shell (index.html + manifest + icons) at install.
//   - For same-origin GETs, use a stale-while-revalidate style cache so users
//     see something instantly and get fresh content on the next load.
//   - NEVER cache anything under /api/ — those are dynamic and must always
//     hit the server (feed, messages, auth, etc.).
//   - Cache Cloudinary images/videos with a cache-first policy so posts load
//     instantly on repeat visits.
//
// SW version bump (2026-02): v2. Fixes a hard bug where a broken origin
// response (e.g. Cloudflare 520 during sign-in) caused staleWhileRevalidate
// to resolve to `undefined`, which throws an unhandled TypeError inside the
// fetch handler and locks the user out until a hard-refresh. All handlers
// now guarantee a valid Response is returned in every code path.

const CACHE_VERSION = 'ace-chasers-v2';
const APP_SHELL_CACHE = `${CACHE_VERSION}-shell`;
const RUNTIME_CACHE   = `${CACHE_VERSION}-runtime`;
const MEDIA_CACHE     = `${CACHE_VERSION}-media`;

const APP_SHELL = [
  '/',
  '/manifest.webmanifest',
  '/apple-touch-icon.png',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(APP_SHELL_CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch(() => {}) // don't block install if a precache asset is missing
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => !k.startsWith(CACHE_VERSION))
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// Allow the app to force-reset the SW after a failed auth handshake — the
// page just posts {type:'CLEAR_CACHES'} and we drop every runtime cache.
self.addEventListener('message', (event) => {
  if (event?.data?.type === 'CLEAR_CACHES') {
    event.waitUntil(
      caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
    );
  }
});

// Empty fallback used whenever a network or cache path yields nothing —
// returning `undefined` from a fetch handler is what triggers the
// TypeError that was locking users out on sign-in failures.
function offlineFallback() {
  return new Response('', {
    status: 504,
    statusText: 'Gateway Timeout',
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}

// A response is safely cacheable only if it's a fully-buffered `basic`
// (same-origin) 200. Opaque / redirect / partial / 5xx responses can
// throw when cloned or replayed. This is the main hardening.
function isCacheable(res) {
  return !!(res && res.ok && res.status === 200 && res.type === 'basic');
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try {
    url = new URL(req.url);
  } catch {
    return; // malformed URL — let the browser handle it
  }

  // Never cache API traffic — always go to the network.
  if (url.pathname.startsWith('/api/')) return;

  // Cloudinary media: cache-first, they're immutable at their versioned URL.
  if (url.hostname.endsWith('res.cloudinary.com')) {
    event.respondWith(cacheFirst(req, MEDIA_CACHE));
    return;
  }

  // Same-origin app shell / static assets: stale-while-revalidate.
  if (url.origin === self.location.origin) {
    event.respondWith(staleWhileRevalidate(req, RUNTIME_CACHE));
  }
});

async function cacheFirst(req, cacheName) {
  try {
    const cache = await caches.open(cacheName);
    const hit = await cache.match(req);
    if (hit) return hit;
    try {
      const res = await fetch(req);
      if (isCacheable(res)) {
        try { await cache.put(req, res.clone()); } catch { /* body might have been read */ }
      }
      return res || offlineFallback();
    } catch {
      return hit || offlineFallback();
    }
  } catch {
    return offlineFallback();
  }
}

async function staleWhileRevalidate(req, cacheName) {
  let cache;
  try {
    cache = await caches.open(cacheName);
  } catch {
    // Cache API blew up — fall back to the network with a safe wrapper.
    try {
      const res = await fetch(req);
      return res || offlineFallback();
    } catch {
      return offlineFallback();
    }
  }

  let hit;
  try {
    hit = await cache.match(req);
  } catch {
    hit = null;
  }

  // Kick off a network revalidation but never let it reject uncaught.
  const fetchPromise = fetch(req)
    .then((res) => {
      if (isCacheable(res)) {
        cache.put(req, res.clone()).catch(() => {}); // fire-and-forget
      }
      return res;
    })
    .catch(() => null);

  if (hit) return hit;
  const fresh = await fetchPromise;
  return fresh || offlineFallback();
}
