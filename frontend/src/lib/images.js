const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export function resolveImageUrl(path) {
  if (!path) return null;
  if (path.startsWith('http')) return path;
  return `${BACKEND_URL}${path}`;
}
