import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import { useMatchStore } from '../store/matchStore';

/**
 * MessageComposeModal
 *
 * A reusable popover for sending a quick message without leaving the page.
 *
 * Two modes:
 *  1. With a fixed `recipient` ({ uid, name, profilePictureUrl }) — used from
 *     Discovery cards and PlayerProfile. The recipient header is shown and
 *     the message textarea is auto-focused.
 *  2. With `pickFromFriends=true` and no `recipient` — used from the Messages
 *     inbox "New message" button. Lets the user search their friends list
 *     and pick a recipient before composing.
 *
 * Calls `onSent(recipient, message)` after a successful send so the caller can
 * refresh their thread list, redirect, etc. Always closes via `onClose`.
 */
export default function MessageComposeModal({
  recipient: initialRecipient = null,
  pickFromFriends = false,
  onClose,
  onSent,
}) {
  const friends = useMatchStore((s) => s.friends);
  const fetchFriends = useMatchStore((s) => s.fetchFriends);

  const [recipient, setRecipient] = useState(initialRecipient);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const textareaRef = useRef(null);

  useEffect(() => {
    if (pickFromFriends && (!friends || friends.length === 0)) {
      fetchFriends();
    }
  }, [pickFromFriends, friends, fetchFriends]);

  // Auto-focus the textarea once a recipient is chosen.
  useEffect(() => {
    if (recipient && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [recipient]);

  // Close on ESC.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const filteredFriends = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = friends || [];
    if (!q) return list;
    return list.filter(
      (f) => (f.name || '').toLowerCase().includes(q) || f.uid.toLowerCase().includes(q),
    );
  }, [friends, query]);

  const handleSend = async () => {
    const body = text.trim();
    if (!body || !recipient || sending) return;
    setSending(true);
    setError('');
    try {
      const res = await api.post(`/messages/${recipient.uid}`, { body });
      onSent?.(recipient, res.data);
      onClose?.();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not send message');
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="message-compose-overlay"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        data-testid="message-compose-modal"
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-200">
          <h2 className="text-lg font-bold text-disc-green flex-1">
            {recipient
              ? `Message ${recipient.name || 'Player'}`
              : 'New message'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-800 font-bold text-xl leading-none"
            aria-label="Close"
            data-testid="message-compose-close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        {!recipient ? (
          <div className="p-5 flex-1 overflow-hidden flex flex-col">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search players you've added…"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-disc-green mb-3"
              data-testid="message-compose-search"
              autoFocus
            />
            <div className="overflow-y-auto flex-1 -mx-2">
              {(friends?.length || 0) === 0 ? (
                <p className="text-sm text-gray-500 px-2 py-4">
                  You haven&apos;t added any players yet. Head to Discovery and tap 🤝 Player on someone to send a request.
                </p>
              ) : filteredFriends.length === 0 ? (
                <p className="text-sm text-gray-500 px-2 py-4">
                  No players match &quot;{query}&quot;.
                </p>
              ) : (
                <ul>
                  {filteredFriends.map((f) => (
                    <li key={f.uid}>
                      <button
                        type="button"
                        onClick={() => setRecipient(f)}
                        className="w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-gray-100 transition text-left"
                        data-testid={`message-compose-pick-${f.uid}`}
                      >
                        <img
                          src={resolveImageUrl(f.profilePictureUrl) || DEFAULT_AVATAR}
                          alt={f.name || 'Player'}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                        <span className="font-semibold text-gray-800 truncate">
                          {f.name || 'Player'}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ) : (
          <div className="p-5 flex flex-col gap-3">
            {/* Recipient pill */}
            <div className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
              <img
                src={resolveImageUrl(recipient.profilePictureUrl) || DEFAULT_AVATAR}
                alt={recipient.name || 'Player'}
                className="w-10 h-10 rounded-full object-cover"
              />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-800 truncate">
                  To: {recipient.name || 'Player'}
                </p>
              </div>
              {pickFromFriends && initialRecipient === null && (
                <button
                  type="button"
                  onClick={() => setRecipient(null)}
                  className="text-xs text-disc-green font-semibold hover:underline"
                  data-testid="message-compose-change-recipient"
                >
                  Change
                </button>
              )}
            </div>

            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Type your message…"
              maxLength={2000}
              rows={4}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-disc-green resize-none"
              data-testid="message-compose-textarea"
            />

            {error && (
              <p className="text-sm text-red-600" data-testid="message-compose-error">
                {error}
              </p>
            )}

            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-400">
                {text.length}/2000 · ⌘/Ctrl+Enter to send
              </p>
              <button
                type="button"
                onClick={handleSend}
                disabled={sending || !text.trim()}
                className="bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white font-bold px-5 py-2 rounded-lg transition"
                data-testid="message-compose-send"
              >
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
