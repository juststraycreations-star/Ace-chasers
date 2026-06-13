import { useState } from 'react';
import { useMessageStore } from '../store/messageStore';

// Mock conversations
const MOCK_CONVERSATIONS = [
  {
    id: 1,
    name: 'Sarah',
    lastMessage: 'Sure! How about next weekend?',
    timestamp: '2 hours ago',
    unread: true,
    avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=50&h=50&fit=crop',
  },
  {
    id: 2,
    name: 'Jessica',
    lastMessage: 'I love Rattlesnake Ledge!',
    timestamp: '1 day ago',
    unread: false,
    avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=50&h=50&fit=crop',
  },
];

const MOCK_MESSAGES = {
  1: [
    { id: 1, senderId: 'other', text: 'Hey! I really liked your profile', timestamp: '2 hours ago' },
    { id: 2, senderId: 'me', text: 'Thanks! Love your bio too', timestamp: '2 hours ago' },
    { id: 3, senderId: 'other', text: 'Want to play a round sometime?', timestamp: '2 hours ago' },
    { id: 4, senderId: 'me', text: 'Absolutely! When are you free?', timestamp: '2 hours ago' },
    { id: 5, senderId: 'other', text: 'Sure! How about next weekend?', timestamp: '2 hours ago' },
  ],
};

export default function Messages() {
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [messageText, setMessageText] = useState('');
  const [conversations, setConversations] = useState(MOCK_CONVERSATIONS);
  const [messages, setMessages] = useState(MOCK_MESSAGES);

  const handleSendMessage = () => {
    if (!messageText.trim() || !selectedConversation) return;

    const newMessage = {
      id: Date.now(),
      senderId: 'me',
      text: messageText,
      timestamp: 'now',
    };

    setMessages(prev => ({
      ...prev,
      [selectedConversation]: [...(prev[selectedConversation] || []), newMessage],
    }));

    setMessageText('');
  };

  const currentMessages = selectedConversation ? messages[selectedConversation] : [];
  const currentConversation = conversations.find(c => c.id === selectedConversation);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-[600px]">
        {/* Conversations List */}
        <div className="bg-white rounded-lg shadow overflow-hidden flex flex-col">
          <div className="bg-disc-green text-white p-4">
            <h2 className="text-2xl font-bold">Messages</h2>
          </div>

          <div className="overflow-y-auto flex-1">
            {conversations.map(conv => (
              <div
                key={conv.id}
                onClick={() => setSelectedConversation(conv.id)}
                className={`p-4 border-b cursor-pointer transition ${
                  selectedConversation === conv.id
                    ? 'bg-disc-green/10 border-disc-green'
                    : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center gap-3">
                  <img
                    src={conv.avatar}
                    alt={conv.name}
                    className="w-12 h-12 rounded-full"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-gray-800">{conv.name}</p>
                    <p className="text-sm text-gray-600 truncate">{conv.lastMessage}</p>
                    <p className="text-xs text-gray-500">{conv.timestamp}</p>
                  </div>
                  {conv.unread && (
                    <div className="w-3 h-3 bg-disc-gold rounded-full"></div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat Area */}
        {selectedConversation ? (
          <div className="md:col-span-2 bg-white rounded-lg shadow flex flex-col">
            {/* Header */}
            <div className="bg-disc-green text-white p-4 border-b">
              <h3 className="text-xl font-bold">{currentConversation?.name}</h3>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {currentMessages.map(msg => (
                <div
                  key={msg.id}
                  className={`flex ${msg.senderId === 'me' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-xs px-4 py-2 rounded-lg ${
                      msg.senderId === 'me'
                        ? 'bg-disc-green text-white'
                        : 'bg-gray-200 text-gray-800'
                    }`}
                  >
                    <p>{msg.text}</p>
                    <p className="text-xs mt-1 opacity-70">{msg.timestamp}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Input */}
            <div className="border-t p-4 flex gap-2">
              <input
                type="text"
                placeholder="Type a message..."
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              />
              <button
                onClick={handleSendMessage}
                className="bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 px-6 rounded-lg transition"
              >
                Send
              </button>
            </div>
          </div>
        ) : (
          <div className="md:col-span-2 bg-white rounded-lg shadow flex items-center justify-center">
            <p className="text-gray-500 text-lg">Select a conversation to start messaging</p>
          </div>
        )}
      </div>
    </div>
  );
}
