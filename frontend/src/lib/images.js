// Hostname-aware backend URL resolution.
// On *.acechasers.net we ALWAYS route to the Emergent production host
// regardless of any (possibly misconfigured) build-time env var. See
// lib/api.js for the full rationale.
function resolveBackendUrl() {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host.endsWith('acechasers.net')) {
      return 'https://frisbee-favorites.emergent.host';
    }
  }
  const fromEnv = process.env.REACT_APP_BACKEND_URL;
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined') return window.location.origin;
  return '';
}

const BACKEND_URL = resolveBackendUrl();

export function resolveImageUrl(path) {
  if (!path) return null;
  if (path.startsWith('http')) return path;
  return `${BACKEND_URL}${path}`;
}
