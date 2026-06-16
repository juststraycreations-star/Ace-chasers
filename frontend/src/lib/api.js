import axios from 'axios';
import { getFirebaseAuth, firebaseConfigured } from './firebase';

// Hostname-aware backend URL resolution.
// PRIORITY ORDER (intentional — do not reorder without thinking about it):
//   1. If we're running on the public custom domain (*.acechasers.net),
//      always route to the Emergent production host. This wins over env
//      vars so a misconfigured deployment can't break sign-in.
//   2. If REACT_APP_BACKEND_URL is set at build time, honor it.
//   3. Otherwise fall back to same-origin (useful for localhost dev).
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

export const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
});

api.interceptors.request.use(async (config) => {
  if (firebaseConfigured) {
    const auth = getFirebaseAuth();
    const user = auth?.currentUser;
    if (user) {
      const token = await user.getIdToken();
      config.headers.Authorization = `Bearer ${token}`;
    }
  } else {
    // Dev fallback: when Firebase keys are not configured we ship a synthetic
    // unsigned JWT so the backend (also running in dev mode) can identify the
    // local user. Stored as `dev_uid` in localStorage by Login/SignUp.
    const devToken = localStorage.getItem('ace_dev_token');
    if (devToken) {
      config.headers.Authorization = `Bearer ${devToken}`;
    }
  }
  return config;
});

export default api;
