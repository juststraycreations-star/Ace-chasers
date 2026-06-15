import { create } from 'zustand';
import { api } from '../lib/api';

/**
 * API-backed match store.
 * - `deck`     : players returned by GET /api/discovery (filtered server-side).
 * - `likes`    : entries returned by GET /api/likes ({ player, likedAt,
 *                matched, friended }).
 * Actions mutate server state then refresh; we keep them simple and let the
 * source of truth live in Mongo.
 */
export const useMatchStore = create((set, get) => ({
  deck: [],
  likes: [],
  loading: false,
  error: null,

  fetchDeck: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.get('/discovery');
      set({ deck: res.data, loading: false });
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message, loading: false });
    }
  },

  fetchLikes: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.get('/likes');
      set({ likes: res.data, loading: false });
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message, loading: false });
    }
  },

  swipe: async (player, action) => {
    if (!player) return { matched: false };
    // Optimistically remove from the deck.
    set((state) => ({ deck: state.deck.filter((p) => p.uid !== player.uid) }));
    try {
      const res = await api.post('/swipes', { target_uid: player.uid, action });
      if (action === 'like') {
        // Refresh likes so the new entry shows up with the correct match flag.
        await get().fetchLikes();
      }
      return res.data;
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
      return { matched: false };
    }
  },

  likePlayer: (player) => get().swipe(player, 'like'),
  passPlayer: (player) => get().swipe(player, 'pass'),

  sendFriendRequest: async (player) => {
    if (!player) return { matched: false };
    set((state) => ({ deck: state.deck.filter((p) => p.uid !== player.uid) }));
    try {
      const res = await api.post(`/friend-requests/${player.uid}`);
      await get().fetchLikes();
      return res.data;
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
      return { matched: false };
    }
  },

  inbox: { incoming_likes: [], incoming_friend_requests: [] },
  fetchInbox: async () => {
    try {
      const res = await api.get('/inbox');
      set({ inbox: res.data });
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
    }
  },
  acceptFriendRequest: async (fromUid) => {
    try {
      await api.post(`/friend-requests/${fromUid}/accept`);
      await Promise.all([get().fetchInbox(), get().fetchLikes()]);
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
    }
  },
  declineFriendRequest: async (fromUid) => {
    try {
      await api.post(`/friend-requests/${fromUid}/decline`);
      await get().fetchInbox();
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
    }
  },

  addFriend: async (uid) => {
    try {
      await api.post(`/matches/${uid}/friend`);
      await get().fetchLikes();
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
    }
  },

  removeLike: async (uid) => {
    set((state) => ({ likes: state.likes.filter((l) => l.player.uid !== uid) }));
    try {
      await api.delete(`/likes/${uid}`);
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message });
      await get().fetchLikes();
    }
  },

  reset: () => set({ deck: [], likes: [], inbox: { incoming_likes: [], incoming_friend_requests: [] }, loading: false, error: null }),
}));
