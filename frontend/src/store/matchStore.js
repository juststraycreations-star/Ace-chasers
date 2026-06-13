import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Match Store
 * - Tracks the user's swipe history.
 * - `likedPlayers` is a map of playerId -> { player, likedAt, matched, friended }
 *   so the Likes page can render the profiles you've liked even after they leave
 *   the discovery deck.
 * - For demo purposes, a subset of liked players are marked as `matched: true`
 *   (i.e. they liked you back), which surfaces the "Add Friend" link on the Likes
 *   page.
 */

// Player IDs that, when liked by the user, will be auto-marked as a mutual match.
// In a real app this would come from a backend webhook / realtime channel.
const MUTUAL_LIKE_IDS = new Set([1, 3]);

export const useMatchStore = create(
  persist(
    (set, get) => ({
      currentPlayerIndex: 0,
      // playerId -> { player, likedAt, matched, friended }
      likedPlayers: {},
      // playerId -> { player, passedAt }
      passedPlayers: {},
      loading: false,

      nextPlayer: () =>
        set((state) => ({ currentPlayerIndex: state.currentPlayerIndex + 1 })),

      likePlayer: (player) =>
        set((state) => {
          if (!player) return state;
          const isMutual = MUTUAL_LIKE_IDS.has(player.id);
          return {
            likedPlayers: {
              ...state.likedPlayers,
              [player.id]: {
                player,
                likedAt: new Date().toISOString(),
                matched: isMutual,
                friended: false,
              },
            },
            currentPlayerIndex: state.currentPlayerIndex + 1,
          };
        }),

      passPlayer: (player) =>
        set((state) => {
          if (!player) return state;
          return {
            passedPlayers: {
              ...state.passedPlayers,
              [player.id]: { player, passedAt: new Date().toISOString() },
            },
            currentPlayerIndex: state.currentPlayerIndex + 1,
          };
        }),

      /**
       * Mark a matched-like as friended (used by the "Add Friend" link on the
       * Likes page).
       */
      addFriend: (playerId) =>
        set((state) => {
          const entry = state.likedPlayers[playerId];
          if (!entry) return state;
          return {
            likedPlayers: {
              ...state.likedPlayers,
              [playerId]: { ...entry, friended: true },
            },
          };
        }),

      /**
       * Remove a like (used to "unlike" from the Likes page).
       */
      removeLike: (playerId) =>
        set((state) => {
          const { [playerId]: _removed, ...rest } = state.likedPlayers;
          return { likedPlayers: rest };
        }),

      resetIndex: () => set({ currentPlayerIndex: 0 }),
      reset: () =>
        set({
          currentPlayerIndex: 0,
          likedPlayers: {},
          passedPlayers: {},
        }),
    }),
    {
      name: 'ace-chasers-matches',
      partialize: (state) => ({
        currentPlayerIndex: state.currentPlayerIndex,
        likedPlayers: state.likedPlayers,
        passedPlayers: state.passedPlayers,
      }),
    }
  )
);
