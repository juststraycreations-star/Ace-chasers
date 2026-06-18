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
  deckCursor: null,
  deckHasMore: true,
  likes: [],
  loading: false,
  error: null,

  fetchDeck: async () => {
    set({ loading: true, error: null, deck: [], deckCursor: null, deckHasMore: true });
    try {
      const res = await api.get('/discovery');
      set({
        deck: res.data.players || [],
        deckCursor: res.data.next_cursor || null,
        deckHasMore: !!res.data.next_cursor,
        loading: false,
      });
    } catch (err) {
      set({ error: err?.response?.data?.detail || err.message, loading: false });
    }
  },

  loadMoreDeck: async () => {
    const { deckCursor, deckHasMore, loading } = get();
    if (!deckHasMore || !deckCursor || loading) return;
    set({ loading: true, error: null });
    try {
      const res = await api.get('/discovery', { params: { before: deckCursor } });
      set((state) => ({
        deck: [...state.deck, ...(res.data.players || [])],
        deckCursor: res.data.next_cursor || null,
        deckHasMore: !!res.data.next_cursor,
        loading: false,
      }));
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
    // Optimistic: mark as "request sent" so the UI updates immediately. Do
    // NOT remove from deck — user explicitly asked to keep them visible
    // until they're actual friends.
    set((state) => ({
      inbox: {
        ...state.inbox,
        sent_friend_request_uids: Array.from(
          new Set([...(state.inbox?.sent_friend_request_uids || []), player.uid])
        ),
      },
    }));
    try {
      const res = await api.post(`/friend-requests/${player.uid}`);
      await Promise.all([get().fetchInbox(), get().fetchLikes()]);
      return res.data;
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || 'Friend request failed';
      console.error('sendFriendRequest failed:', err);
      // Roll back the optimistic update on failure.
      set((state) => ({
        inbox: {
          ...state.inbox,
          sent_friend_request_uids: (state.inbox?.sent_friend_request_uids || []).filter(
            (u) => u !== player.uid
          ),
        },
        error: message,
      }));
      return { matched: false, error: message };
    }
  },

  friends: [],
  fetchFriends: async () => {
    try {
      const res = await api.get('/friends');
      set({ friends: res.data });
    } catch (err) {
      console.error('fetchFriends failed:', err);
    }
  },

  inbox: { incoming_likes: [], incoming_friend_requests: [], sent_friend_request_uids: [], friend_uids: [] },
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

  reset: () => set({ deck: [], deckCursor: null, deckHasMore: true, likes: [], friends: [], inbox: { incoming_likes: [], incoming_friend_requests: [], sent_friend_request_uids: [], friend_uids: [] }, loading: false, error: null }),
}));
