import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      loading: false,
      error: null,

      login: (userData) =>
        set({
          user: userData,
          isAuthenticated: true,
          error: null,
        }),

      logout: () =>
        set({
          user: null,
          isAuthenticated: false,
        }),

      /**
       * Merge partial fields into the authenticated user object.
       */
      updateUser: (patch) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...patch } : state.user,
        })),

      setError: (error) => set({ error }),
      setLoading: (loading) => set({ loading }),
    }),
    {
      name: 'ace-chasers-auth',
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);
