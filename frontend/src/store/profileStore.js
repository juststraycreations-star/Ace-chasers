import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Profile Store
 * Persists user profile data in localStorage (per-user via dynamic key).
 * Provides fetchProfile, saveProfile and updateProfileField helpers used by Profile.jsx.
 */
export const useProfileStore = create(
  persist(
    (set, get) => ({
      // Map of userId -> profile object
      profiles: {},
      currentProfile: null,
      loading: false,
      error: null,

      /**
       * Fetch (load) profile for a user from local persistence.
       * Returns null if no profile exists yet.
       */
      fetchProfile: async (userId) => {
        set({ loading: true, error: null });
        try {
          const profile = get().profiles[userId] || null;
          set({ currentProfile: profile, loading: false });
          return profile;
        } catch (err) {
          set({ error: err.message, loading: false });
          return null;
        }
      },

      /**
       * Save profile for a user. Persists to localStorage automatically.
       */
      saveProfile: async (userId, profile) => {
        set({ loading: true, error: null });
        try {
          set((state) => ({
            profiles: { ...state.profiles, [userId]: profile },
            currentProfile: profile,
            loading: false,
          }));
          return profile;
        } catch (err) {
          set({ error: err.message, loading: false });
          throw err;
        }
      },

      /**
       * Update a single field in the current profile (optimistic).
       */
      updateProfileField: (userId, field, value) =>
        set((state) => {
          const existing = state.profiles[userId] || {};
          const updated = { ...existing, [field]: value };
          return {
            profiles: { ...state.profiles, [userId]: updated },
            currentProfile: updated,
          };
        }),

      reset: () => set({ profiles: {}, currentProfile: null, loading: false, error: null }),
    }),
    {
      name: 'ace-chasers-profiles',
      partialize: (state) => ({ profiles: state.profiles }),
    }
  )
);

export default useProfileStore;
