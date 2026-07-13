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

const CACHE_VERSION = 'ace-chasers-v1';
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
    caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
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

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

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
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    return hit || Response.error();
  }
}

async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  const fetchPromise = fetch(req)
    .then((res) => {
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    })
    .catch(() => hit);
  return hit || fetchPromise;
}
