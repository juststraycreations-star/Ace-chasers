import { useEffect } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { firebaseConfigured, getFirebaseAuth } from '../lib/firebase';
import { getStoredDevUser } from '../lib/devAuth';
import { api } from '../lib/api';

/**
 * Mounts once at the top of the app and:
 *  1. Subscribes to Firebase auth state (when configured) so the user object
 *     stays in sync after refresh / sign-out.
 *  2. Falls back to the dev session (localStorage) when Firebase keys aren't
 *     set so we can still build / test end-to-end.
 *  3. Calls POST /api/auth/sync to upsert the user record + seed inbound
 *     demo likes, then loads the full profile.
 */
export default function AuthProvider({ children }) {
  const setUser = useAuthStore((s) => s.setUser);
  const setProfile = useAuthStore((s) => s.setProfile);
  const setAuthReady = useAuthStore((s) => s.setAuthReady);

  useEffect(() => {
    let unsub = () => {};

    async function syncProfile() {
      try {
        const sync = await api.post('/auth/sync');
        setProfile(sync.data);
      } catch (err) {
        console.warn('auth/sync failed:', err?.response?.data || err.message);
      }
    }

    if (firebaseConfigured) {
      const auth = getFirebaseAuth();
      unsub = onAuthStateChanged(auth, async (fbUser) => {
        if (fbUser) {
          setUser({
            uid: fbUser.uid,
            email: fbUser.email,
            name: fbUser.displayName,
            photoURL: fbUser.photoURL,
          });
          await syncProfile();
        } else {
          setUser(null);
          setProfile(null);
        }
        setAuthReady(true);
      });
    } else {
      // Dev fallback: use stored localStorage session if any.
      const devUser = getStoredDevUser();
      if (devUser) {
        setUser(devUser);
        syncProfile().finally(() => setAuthReady(true));
      } else {
        setAuthReady(true);
      }
    }

    return () => unsub();
  }, [setUser, setProfile, setAuthReady]);

  return children;
}
