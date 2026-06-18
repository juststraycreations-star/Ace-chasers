import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '../lib/api';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import MessageComposeModal from '../components/MessageComposeModal';

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return new Date(iso).toLocaleDateString();
}

export default function Messages() {
  const location = useLocation();
  const deepLinkUid = location.state?.withUid || null;
  const deepLinkName = location.state?.name || null;

  const [threads, setThreads] = useState([]);
  const [selected, setSelected] = useState(null); // { uid, name, profilePictureUrl }
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [composeOpen, setComposeOpen] = useState(false);
  const scrollRef = useRef(null);

  const refreshThreads = async () => {
    try {
      const res = await api.get('/messages/threads');
      setThreads(res.data || []);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setLoadingThreads(false);
    }
  };

  useEffect(() => {
    refreshThreads();
  }, []);

  // Deep-link: if PlayerProfile/Discovery sent us with a target uid, open it.
  useEffect(() => {
    if (deepLinkUid && (!selected || selected.uid !== deepLinkUid)) {
      (async () => {
        try {
          const r = await api.get(`/users/${deepLinkUid}`);
          setSelected({
            uid: deepLinkUid,
            name: r.data.name || deepLinkName || 'Player',
            profilePictureUrl: r.data.profilePictureUrl,
          });
        } catch {
          setSelected({ uid: deepLinkUid, name: deepLinkName || 'Player' });
        }
      })();
    }
  }, [deepLinkUid, deepLinkName, selected]);

  // Load messages whenever the selected thread changes.
  useEffect(() => {
    if (!selected) return undefined;
    let cancelled = false;
    setLoadingMessages(true);
    (async () => {
      try {
        const res = await api.get(`/messages/${selected.uid}`);
        if (!cancelled) setMessages(res.data || []);
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || err.message);
      } finally {
        if (!cancelled) setLoadingMessages(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const send = async () => {
    const body = text.trim();
    if (!body || !selected || sending) return;
    setSending(true);
    try {
      const res = await api.post(`/messages/${selected.uid}`, { body });
      setMessages((prev) => [...prev, res.data]);
      setText('');
      refreshThreads();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="messages-view">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-[600px]">
        {/* Threads list */}
        <div
          className="bg-white rounded-lg shadow overflow-hidden flex flex-col"
          data-testid="messages-threads"
        >
          <div className="bg-disc-green text-white p-4 flex items-center justify-between gap-3">
            <h2 className="text-2xl font-bold">Messages</h2>
            <button
              type="button"
              onClick={() => setComposeOpen(true)}
              className="bg-white text-disc-green font-bold text-sm px-3 py-1.5 rounded-full hover:bg-disc-gold hover:text-white transition flex items-center gap-1"
              data-testid="messages-new-btn"
              title="Start a new message"
            >
              ✏️ New
            </button>
          </div>
          <div className="overflow-y-auto flex-1">
            {loadingThreads ? (
              <p className="p-4 text-sm text-gray-500">Loading conversations…</p>
            ) : threads.length === 0 ? (
              <div className="p-4 text-sm text-gray-500">
                No conversations yet. Tap{' '}
                <button
                  type="button"
                  className="text-disc-green font-semibold hover:underline"
                  onClick={() => setComposeOpen(true)}
                  data-testid="messages-empty-new-btn"
                >
                  ✏️ New
                </button>{' '}
                above or visit a player&apos;s{' '}
                <Link to="/discovery" className="text-disc-green font-semibold hover:underline">
                  profile
                </Link>{' '}
                and tap 💬 Message to start one.
              </div>
            ) : (
              threads.map((t) => (
                <button
                  type="button"
                  key={t.with_user.uid}
                  onClick={() =>
                    setSelected({
                      uid: t.with_user.uid,
                      name: t.with_user.name,
                      profilePictureUrl: t.with_user.profilePictureUrl,
                    })
                  }
                  className={`w-full text-left p-4 border-b transition ${
                    selected?.uid === t.with_user.uid
                      ? 'bg-disc-green/10 border-disc-green'
                      : 'hover:bg-gray-50'
                  }`}
                  data-testid={`thread-${t.with_user.uid}`}
                >
                  <div className="flex items-center gap-3">
                    <img
                      src={resolveImageUrl(t.with_user.profilePictureUrl) || DEFAULT_AVATAR}
                      alt={t.with_user.name || 'Player'}
                      className="w-12 h-12 rounded-full object-cover"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-gray-800 truncate">
                        {t.with_user.name || 'Player'}
                      </p>
                      <p className="text-sm text-gray-600 truncate">{t.last_message}</p>
                      <p className="text-xs text-gray-500">{timeAgo(t.last_at)}</p>
                    </div>
                    {t.unread > 0 && (
                      <span
                        className="bg-disc-gold text-disc-green text-[10px] font-bold rounded-full min-w-[20px] h-[20px] px-1 flex items-center justify-center"
                        data-testid={`thread-unread-${t.with_user.uid}`}
                      >
                        {t.unread > 9 ? '9+' : t.unread}
                      </span>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Chat area */}
        {selected ? (
          <div
            className="md:col-span-2 bg-white rounded-lg shadow flex flex-col"
            data-testid="messages-chat"
          >
            <div className="bg-disc-green text-white p-4 border-b flex items-center gap-3">
              <Link to={`/players/${selected.uid}`} className="flex items-center gap-3 flex-1 hover:opacity-90">
                <img
                  src={resolveImageUrl(selected.profilePictureUrl) || DEFAULT_AVATAR}
                  alt={selected.name || 'Player'}
                  className="w-10 h-10 rounded-full object-cover border-2 border-white"
                />
                <h3 className="text-xl font-bold">{selected.name || 'Player'}</h3>
              </Link>
            </div>

            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50"
              data-testid="messages-list"
            >
              {loadingMessages ? (
                <p className="text-center text-gray-400 text-sm">Loading…</p>
              ) : messages.length === 0 ? (
                <p className="text-center text-gray-400 text-sm italic">
                  No messages yet. Say hi! 👋
                </p>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={`flex ${m.is_mine ? 'justify-end' : 'justify-start'}`}
                    data-testid={`message-${m.id}`}
                  >
                    <div
                      className={`max-w-[75%] px-4 py-2 rounded-2xl ${
                        m.is_mine
                          ? 'bg-disc-green text-white rounded-br-sm'
                          : 'bg-white text-gray-800 border border-gray-200 rounded-bl-sm'
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap break-words">{m.body}</p>
                      <p className={`text-[10px] mt-1 ${m.is_mine ? 'text-white/70' : 'text-gray-400'}`}>
                        {timeAgo(m.created_at)}
                      </p>
                    </div>
                  </div>
                ))
              )}
              {error && (
                <p className="text-xs text-red-500 text-center" data-testid="messages-error">
                  {error}
                </p>
              )}
            </div>

            <div className="border-t p-3 flex gap-2 bg-white">
              <input
                type="text"
                placeholder="Type a message…"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                maxLength={2000}
                className="flex-1 border border-gray-300 rounded-full px-4 py-2 text-sm focus:outline-none focus:border-disc-green"
                data-testid="message-input"
              />
              <button
                type="button"
                onClick={send}
                disabled={sending || !text.trim()}
                className="bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white font-bold py-2 px-5 rounded-full transition"
                data-testid="message-send-btn"
              >
                Send
              </button>
            </div>
          </div>
        ) : (
          <div
            className="md:col-span-2 bg-white rounded-lg shadow flex items-center justify-center"
            data-testid="messages-empty"
          >
            <div className="text-center">
              <p className="text-gray-500 text-lg mb-3">Select a conversation to start messaging</p>
              <button
                type="button"
                onClick={() => setComposeOpen(true)}
                className="bg-disc-green hover:bg-disc-green/90 text-white font-bold px-5 py-2 rounded-lg transition"
                data-testid="messages-empty-compose-btn"
              >
                ✏️ Start a new message
              </button>
            </div>
          </div>
        )}
      </div>

      {composeOpen && (
        <MessageComposeModal
          pickFromFriends
          onClose={() => setComposeOpen(false)}
          onSent={(recipient, message) => {
            // Drop the user straight into the new thread and refresh.
            setSelected({
              uid: recipient.uid,
              name: recipient.name,
              profilePictureUrl: recipient.profilePictureUrl,
            });
            setMessages((prev) => [...prev, message]);
            refreshThreads();
          }}
        />
      )}
    </div>
  );
}
