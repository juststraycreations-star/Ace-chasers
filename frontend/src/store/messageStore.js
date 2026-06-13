import { create } from 'zustand';

/**
 * Message Store
 * Manages messaging state for conversations and messages
 * Uses Zustand for lightweight state management
 */
export const useMessageStore = create((set, get) => ({
  // State
  conversations: [],
  messages: {}, // { conversationId: [messages] }
  selectedConversation: null,
  loading: false,
  error: null,
  unreadCount: 0,

  // Actions

  /**
   * Initialize conversations (fetch from backend)
   * @param {Array} conversationsList - List of conversations
   */
  setConversations: (conversationsList) =>
    set({
      conversations: conversationsList,
    }),

  /**
   * Add or update a conversation
   * @param {Object} conversation - Conversation object
   */
  addConversation: (conversation) =>
    set((state) => {
      const exists = state.conversations.find((c) => c.id === conversation.id);
      if (exists) {
        return {
          conversations: state.conversations.map((c) =>
            c.id === conversation.id ? conversation : c
          ),
        };
      }
      return {
        conversations: [conversation, ...state.conversations],
      };
    }),

  /**
   * Set active conversation
   * @param {string|number} conversationId - The conversation ID
   */
  selectConversation: (conversationId) =>
    set({
      selectedConversation: conversationId,
    }),

  /**
   * Fetch messages for a conversation
   * @param {string|number} conversationId - The conversation ID
   * @param {Array} messagesList - List of messages
   */
  setMessages: (conversationId, messagesList) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: messagesList,
      },
    })),

  /**
   * Add a single message to a conversation
   * @param {string|number} conversationId - The conversation ID
   * @param {Object} message - Message object
   */
  addMessage: (conversationId, message) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [...(state.messages[conversationId] || []), message],
      },
    })),

  /**
   * Send a message (optimistic update)
   * @param {string|number} conversationId - The conversation ID
   * @param {string} text - The message text
   * @param {string} senderId - The sender ID
   * @returns {Promise<Object>} - The sent message
   */
  sendMessage: async (conversationId, text, senderId) => {
    const state = get();
    
    if (!text.trim()) {
      set({ error: 'Message cannot be empty' });
      return null;
    }

    // Optimistic update
    const optimisticMessage = {
      id: Date.now(),
      senderId,
      text,
      timestamp: new Date().toISOString(),
      status: 'sending',
    };

    set((prevState) => ({
      messages: {
        ...prevState.messages,
        [conversationId]: [
          ...(prevState.messages[conversationId] || []),
          optimisticMessage,
        ],
      },
    }));

    try {
      // Send to backend
      const response = await fetch('/api/messages/send', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify({
          conversationId,
          text,
          senderId,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      const sentMessage = await response.json();

      // Update with real message from backend
      set((prevState) => ({
        messages: {
          ...prevState.messages,
          [conversationId]: prevState.messages[conversationId].map((msg) =>
            msg.id === optimisticMessage.id ? sentMessage : msg
          ),
        },
      }));

      return sentMessage;
    } catch (error) {
      console.error('Send message error:', error);
      
      // Revert optimistic update on error
      set((prevState) => ({
        messages: {
          ...prevState.messages,
          [conversationId]: prevState.messages[conversationId].filter(
            (msg) => msg.id !== optimisticMessage.id
          ),
        },
        error: error.message,
      }));

      throw error;
    }
  },

  /**
   * Mark messages as read
   * @param {string|number} conversationId - The conversation ID
   */
  markAsRead: async (conversationId) => {
    try {
      await fetch(`/api/conversations/${conversationId}/read`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
        },
      });

      // Update conversation unread status
      set((state) => ({
        conversations: state.conversations.map((conv) =>
          conv.id === conversationId ? { ...conv, unread: false } : conv
        ),
      }));
    } catch (error) {
      console.error('Mark as read error:', error);
    }
  },

  /**
   * Fetch conversations from backend
   * @returns {Promise<Array>} - List of conversations
   */
  fetchConversations: async () => {
    set({ loading: true, error: null });
    try {
      const response = await fetch('/api/conversations', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch conversations');
      }

      const data = await response.json();
      set({ conversations: data, loading: false });
      return data;
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  /**
   * Fetch messages for a conversation
   * @param {string|number} conversationId - The conversation ID
   * @returns {Promise<Array>} - List of messages
   */
  fetchMessages: async (conversationId) => {
    set({ loading: true, error: null });
    try {
      const response = await fetch(`/api/conversations/${conversationId}/messages`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch messages');
      }

      const data = await response.json();
      set((state) => ({
        messages: {
          ...state.messages,
          [conversationId]: data,
        },
        loading: false,
      }));
      return data;
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  /**
   * Delete a message
   * @param {string|number} conversationId - The conversation ID
   * @param {string|number} messageId - The message ID
   */
  deleteMessage: async (conversationId, messageId) => {
    try {
      const response = await fetch(`/api/messages/${messageId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to delete message');
      }

      // Remove from state
      set((state) => ({
        messages: {
          ...state.messages,
          [conversationId]: state.messages[conversationId].filter(
            (msg) => msg.id !== messageId
          ),
        },
      }));
    } catch (error) {
      console.error('Delete message error:', error);
      set({ error: error.message });
      throw error;
    }
  },

  /**
   * Clear messages for a conversation
   * @param {string|number} conversationId - The conversation ID
   */
  clearMessages: (conversationId) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [],
      },
    })),

  /**
   * Reset store state
   */
  reset: () =>
    set({
      conversations: [],
      messages: {},
      selectedConversation: null,
      loading: false,
      error: null,
      unreadCount: 0,
    }),

  /**
   * Set loading state
   */
  setLoading: (loading) => set({ loading }),

  /**
   * Set error message
   */
  setError: (error) => set({ error }),
}));

export default useMessageStore;