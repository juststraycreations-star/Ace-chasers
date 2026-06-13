import { create } from 'zustand';

/**
 * Holds the currently authenticated user (Firebase user mapped onto our
 * profile schema) plus the API-loaded profile. NOT persisted - we rely on
 * Firebase's own persistence + AuthProvider rehydration on every load.
 */
export const useAuthStore = create((set, get) => ({
  user: null,            // { uid, email, name, photoURL }
  profile: null,         // full profile loaded from /api/users/me
  isAuthenticated: false,
  authReady: false,      // becomes true once the first auth check completes
  loading: false,
  error: null,
  config: { require_invite: false }, // server-side feature flags

  setConfig: (config) => set({ config }),

  setUser: (user) =>
    set({
      user,
      isAuthenticated: Boolean(user),
    }),

  setProfile: (profile) => set({ profile }),

  patchProfile: (patch) =>
    set((state) => ({
      profile: state.profile ? { ...state.profile, ...patch } : state.profile,
    })),

  setAuthReady: (ready) => set({ authReady: ready }),

  reset: () =>
    set({
      user: null,
      profile: null,
      isAuthenticated: false,
      loading: false,
      error: null,
    }),

  setError: (error) => set({ error }),
  setLoading: (loading) => set({ loading }),
}));
