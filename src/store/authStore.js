import { create } from 'zustand';

export const useAuthStore = create((set) => ({
  user: null,
  isAuthenticated: false,
  loading: false,
  error: null,

  login: (userData) => set({
    user: userData,
    isAuthenticated: true,
    error: null,
  }),

  logout: () => set({
    user: null,
    isAuthenticated: false,
  }),

  setError: (error) => set({ error }),
  setLoading: (loading) => set({ loading }),
}));
