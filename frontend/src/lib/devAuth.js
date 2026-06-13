/**
 * Tiny helper that synthesises an unsigned dev JWT so the app can run
 * end-to-end before the user has supplied Firebase credentials. The backend
 * also has a matching "insecure dev" branch that decodes without
 * verification. Once Firebase env vars are set this code path is bypassed
 * entirely.
 */
function base64UrlEncode(obj) {
  const json = JSON.stringify(obj);
  // btoa works on Latin-1 strings; encode UTF-8 first.
  const b64 = btoa(unescape(encodeURIComponent(json)));
  return b64.replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
}

function randomId() {
  return 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

const DEV_TOKEN_KEY = 'ace_dev_token';
const DEV_USER_KEY = 'ace_dev_user';

export function getStoredDevUser() {
  const raw = localStorage.getItem(DEV_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function makeDevSession({ email, name }) {
  let user = getStoredDevUser();
  if (!user || user.email !== email) {
    user = {
      uid: randomId(),
      email,
      name: name || (email ? email.split('@')[0] : 'Player'),
    };
  }
  const header = base64UrlEncode({ alg: 'none', typ: 'JWT' });
  const payload = base64UrlEncode({
    sub: user.uid,
    uid: user.uid,
    email: user.email,
    name: user.name,
    iat: Math.floor(Date.now() / 1000),
  });
  const token = `${header}.${payload}.`;
  localStorage.setItem(DEV_TOKEN_KEY, token);
  localStorage.setItem(DEV_USER_KEY, JSON.stringify(user));
  return { token, user };
}

export function clearDevSession() {
  localStorage.removeItem(DEV_TOKEN_KEY);
  localStorage.removeItem(DEV_USER_KEY);
}
