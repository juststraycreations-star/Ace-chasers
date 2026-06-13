import axios from 'axios';
import { getFirebaseAuth, firebaseConfigured } from './firebase';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

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
