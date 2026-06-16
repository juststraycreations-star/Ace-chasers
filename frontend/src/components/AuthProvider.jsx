import { useEffect } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { firebaseConfigured, getFirebaseAuth } from '../lib/firebase';
import { clearDevSession, getStoredDevUser } from '../lib/devAuth';
import { api } from '../lib/api';

/**
 * Top-level provider that re-hydrates the session on every page load.
 *  - When a Firebase user is present (or a dev session is stored), we try
 *    `POST /api/auth/sync` first. Only on success do we mark the user as
 *    authenticated. This prevents users with revoked invites / stale local
 *    sessions from slipping into the app shell.
 *  - On sync failure for an *existing* in-progress login, we sign them out
 *    so the next render shows the login screen.
 *
 * The Login / SignUp pages call `/api/auth/sync` themselves and only flip
 * the store on success too — see those files for the redemption + invite
 * flow.
 */
export default function AuthProvider({ children }) {
  const setUser = useAuthStore((s) => s.setUser);
  const setProfile = useAuthStore((s) => s.setProfile);
  const setAuthReady = useAuthStore((s) => s.setAuthReady);
  const setConfig = useAuthStore((s) => s.setConfig);

  useEffect(() => {
    let unsub = () => {};

    // Pull server feature flags up-front so signup screens know whether to
    // show the invite field.
    api.get('/config')
      .then((r) => setConfig(r.data))
      .catch((err) => {
        console.warn('Failed to load /api/config:', err?.message);
      });

    async function rehydrate(userObj, onFail) {
      try {
        const sync = await api.post('/auth/sync', {});
        setUser(userObj);
        setProfile(sync.data);
      } catch (err) {
        console.warn('auth rehydrate failed:', err?.response?.data || err.message);
        await onFail();
        setUser(null);
        setProfile(null);
      } finally {
        setAuthReady(true);
      }
    }

    if (firebaseConfigured) {
      const auth = getFirebaseAuth();
      unsub = onAuthStateChanged(auth, async (fbUser) => {
        if (!fbUser) {
          setUser(null);
          setProfile(null);
          setAuthReady(true);
          return;
        }
        await rehydrate(
          {
            uid: fbUser.uid,
            email: fbUser.email,
            name: fbUser.displayName,
            photoURL: fbUser.photoURL,
          },
          async () => {
            try {
              await auth.signOut();
            } catch {
              /* noop */
            }
          }
        );
      });
    } else {
      const devUser = getStoredDevUser();
      if (devUser) {
        rehydrate(devUser, async () => {
          clearDevSession();
        });
      } else {
        setAuthReady(true);
      }
    }

    return () => unsub();
  }, [setUser, setProfile, setAuthReady, setConfig]);

  return children;
}
