import { create } from 'zustand';

export const useMatchStore = create((set) => ({
  players: [],
  currentPlayerIndex: 0,
  matches: [],
  loading: false,

  setPlayers: (players) => set({ players }),

  nextPlayer: () => set((state) => ({
    currentPlayerIndex: state.currentPlayerIndex + 1,
  })),

  likePlayer: (playerId) => set((state) => ({
    matches: [...state.matches, { playerId, action: 'like', timestamp: new Date() }],
  })),

  passPlayer: (playerId) => set((state) => ({
    matches: [...state.matches, { playerId, action: 'pass', timestamp: new Date() }],
  })),

  setLoading: (loading) => set({ loading }),

  resetIndex: () => set({ currentPlayerIndex: 0 }),
}));
