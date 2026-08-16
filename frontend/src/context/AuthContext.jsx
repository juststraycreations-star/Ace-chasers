/**
 * Bridge between the league app's `useAuth()` API (which the ported
 * league pages expect) and Ace Chasers' existing Firebase-backed
 * `useAuthStore` (Zustand). This lets us reuse the ported league pages
 * verbatim without modifying every `useAuth()` call site.
 *
 * The shape of the returned user matches what the league pages read:
 *   { user_id, name, email, picture }
 */
import { createContext, useContext } from 'react';
import { useAuthStore } from '../store/authStore';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const user = useAuthStore((s) => s.user);
  const profile = useAuthStore((s) => s.profile);
  const bridged = user
    ? {
        user_id: user.uid,
        name: profile?.name || user.displayName || user.email,
        email: user.email,
        picture: profile?.profilePictureUrl || user.photoURL || null,
      }
    : null;

  const value = {
    user: bridged,
    loading: false,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  // Hooks must be called unconditionally per rules-of-hooks. We always
  // read from the store; the provider result (if present) wins, but
  // reading both keeps the hook order stable across every render.
  const storeUser = useAuthStore((s) => s.user);
  const storeProfile = useAuthStore((s) => s.profile);
  if (ctx) return ctx;
  // Provider missing — fall back to the store so a hot-reload landing
  // on a league page doesn't blow up.
  return {
    user: storeUser
      ? {
          user_id: storeUser.uid,
          name: storeProfile?.name || storeUser.displayName || storeUser.email,
          email: storeUser.email,
          picture: storeProfile?.profilePictureUrl || storeUser.photoURL || null,
        }
      : null,
    loading: false,
  };
}
