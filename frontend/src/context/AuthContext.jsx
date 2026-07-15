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
  if (!ctx) {
    // Provider missing — fall back to reading directly from the store so we
    // never crash a league page during a hot reload.
    const user = useAuthStore((s) => s.user);
    const profile = useAuthStore((s) => s.profile);
    return {
      user: user
        ? {
            user_id: user.uid,
            name: profile?.name || user.displayName || user.email,
            email: user.email,
            picture: profile?.profilePictureUrl || user.photoURL || null,
          }
        : null,
      loading: false,
    };
  }
  return ctx;
}
