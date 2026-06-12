import { create } from 'zustand';

export const useMessageStore = create((set) => ({
  conversations: [],
  currentConversation: null,
  messages: [],
  loading: false,

  setConversations: (conversations) => set({ conversations }),

  setCurrentConversation: (conversation) => set({ currentConversation: conversation }),

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  setMessages: (messages) => set({ messages }),

  sendMessage: (conversationId, content, senderId) => {
    const newMessage = {
      id: Date.now(),
      conversationId,
      senderId,
      content,
      timestamp: new Date(),
      read: false,
    };

    set((state) => ({
      messages: [...state.messages, newMessage],
    }));

    return newMessage;
  },

  setLoading: (loading) => set({ loading }),
}));
