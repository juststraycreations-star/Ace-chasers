// Hostname-aware backend URL resolution — see lib/api.js for the rationale.
function resolveBackendUrl() {
  const fromEnv = process.env.REACT_APP_BACKEND_URL;
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host.endsWith('acechasers.net')) {
      return 'https://frisbee-favorites.emergent.host';
    }
    return window.location.origin;
  }
  return '';
}

const BACKEND_URL = resolveBackendUrl();

export function resolveImageUrl(path) {
  if (!path) return null;
  if (path.startsWith('http')) return path;
  return `${BACKEND_URL}${path}`;
}
