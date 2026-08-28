// Hostname-aware backend URL resolution.
// On *.acechasers.net we ALWAYS route to same-origin so media URLs hit the
// same ingress that serves the SPA. See lib/api.js for the full rationale.
function resolveBackendUrl() {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host.endsWith('acechasers.net')) {
      return window.location.origin;
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
