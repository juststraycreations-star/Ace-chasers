import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

const SEEN_KEY = 'ace_seen_friend_request_uids_v1';
const TOAST_MS = 5000;

/**
 * Reads the localStorage-backed set of friend-request uids the user has
 * already been shown a toast / browser notification for. Used so we only
 * surface NEW arrivals between polls — not the entire pending pile every
 * single time.
 */
function readSeen() {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw));
  } catch (_e) {
    return new Set();
  }
}

function writeSeen(uids) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...uids]));
  } catch (_e) {
    /* localStorage may be disabled in private browsing — silently ignore. */
  }
}

/**
 * Bell icon with a red badge that opens an Add / Ignore popover for incoming
 * player (friend) requests. Detects new arrivals between polls of
 * `useMatchStore().inbox` so it can:
 *   - flash an inline toast ("X wants to add you as a player")
 *   - fire a browser notification if the user opted in
 *   - keep the badge count accurate even when the popover is open
 */
export default function NotificationsBell() {
  const inbox = useMatchStore((s) => s.inbox);
  const acceptFriendRequest = useMatchStore((s) => s.acceptFriendRequest);
  const declineFriendRequest = useMatchStore((s) => s.declineFriendRequest);

  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState(null); // { uid, name }
  const containerRef = useRef(null);

  const requests = useMemo(
    () => inbox?.incoming_friend_requests || [],
    [inbox?.incoming_friend_requests],
  );
  const count = requests.length;

  // ---------- New-arrival detection (toast + browser notification) ---------
  useEffect(() => {
    if (requests.length === 0) return;
    const seen = readSeen();
    const fresh = requests.filter((r) => !seen.has(r.from_user.uid));
    if (fresh.length === 0) return;

    // Show inline toast for the most recent fresh request.
    const newest = fresh[0];
    setToast({
      uid: newest.from_user.uid,
      name: newest.from_user.name || 'A player',
      count: fresh.length,
    });
    const t = setTimeout(() => setToast(null), TOAST_MS);

    // Fire a browser notification only if the user opted in via the
    // Notification API.
    if (
      typeof window !== 'undefined' &&
      'Notification' in window &&
      window.Notification.permission === 'granted'
    ) {
      try {
        new window.Notification(
          fresh.length === 1
            ? `Add Player? ${newest.from_user.name || 'New player'} wants to add you`
            : `Add Player? You have ${fresh.length} new player requests`,
          {
            body: 'Open Ace Chasers to accept or ignore.',
            tag: 'ace-friend-requests',
            icon: '/favicon.ico',
          },
        );
      } catch (err) {
        // Permission revoked mid-session or browser blocked it; swallow.
        console.warn('Notification fire failed:', err);
      }
    }

    // Mark these as seen so we don't re-toast on the next poll.
    const next = new Set([...seen, ...fresh.map((r) => r.from_user.uid)]);
    writeSeen(next);
    return () => clearTimeout(t);
  }, [requests]);

  // ---------- Click-outside to close ---------------------------------------
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  // ---------- Actions ------------------------------------------------------
  const handleAccept = useCallback(
    async (uid) => {
      await acceptFriendRequest(uid);
    },
    [acceptFriendRequest],
  );

  const handleIgnore = useCallback(
    async (uid) => {
      await declineFriendRequest(uid);
    },
    [declineFriendRequest],
  );

  const askBrowserPermission = async () => {
    if (!('Notification' in window)) return;
    try {
      await window.Notification.requestPermission();
    } catch (err) {
      console.warn('Notification.requestPermission failed:', err);
    }
  };

  const browserPermission =
    typeof window !== 'undefined' && 'Notification' in window
      ? window.Notification.permission
      : 'unsupported';

  return (
    <div className="relative" ref={containerRef} data-testid="notifications-bell-wrapper">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative font-semibold transition hover:text-disc-gold"
        data-testid="notifications-bell-btn"
        aria-label={`${count} player request${count === 1 ? '' : 's'} pending`}
        title="Player requests"
      >
        <span aria-hidden="true" className="text-xl leading-none">🔔</span>
        {count > 0 && (
          <span
            className="absolute -top-2 -right-3 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] px-1 flex items-center justify-center shadow ring-2 ring-disc-green"
            data-testid="notifications-bell-badge"
          >
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {/* Inline toast */}
      {toast && (
        <div
          className="fixed top-20 right-4 z-[60] bg-white text-gray-800 border border-disc-green/30 rounded-xl shadow-xl px-4 py-3 max-w-xs flex items-start gap-2 animate-in"
          data-testid="notifications-toast"
        >
          <span aria-hidden="true">🤝</span>
          <div className="flex-1 text-sm">
            <p className="font-bold text-disc-green">
              {toast.count > 1
                ? `${toast.count} new player requests`
                : `${toast.name} wants to add you`}
            </p>
            <p className="text-gray-600">
              Tap the bell to{' '}
              <button
                type="button"
                onClick={() => {
                  setToast(null);
                  setOpen(true);
                }}
                className="text-disc-green font-bold underline"
                data-testid="notifications-toast-open"
              >
                review
              </button>
              .
            </p>
          </div>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="text-gray-400 hover:text-gray-700 leading-none font-bold"
            aria-label="Dismiss"
            data-testid="notifications-toast-dismiss"
          >
            ✕
          </button>
        </div>
      )}

      {/* Popover panel */}
      {open && (
        <div
          className="absolute right-0 mt-3 w-80 bg-white text-gray-800 rounded-xl shadow-2xl border border-gray-100 overflow-hidden z-50"
          data-testid="notifications-panel"
        >
          <div className="px-4 py-3 bg-disc-green/5 border-b border-gray-100 flex items-center justify-between">
            <p className="font-bold text-disc-green">Player requests</p>
            <span className="text-xs text-gray-500" data-testid="notifications-panel-count">
              {count}
            </span>
          </div>

          {browserPermission === 'default' && (
            <button
              type="button"
              onClick={askBrowserPermission}
              className="w-full text-left text-xs text-disc-green hover:bg-disc-green/5 font-semibold px-4 py-2 border-b border-gray-100"
              data-testid="notifications-enable-browser-btn"
            >
              🔔 Enable browser notifications
            </button>
          )}

          {count === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-500 text-center" data-testid="notifications-empty">
              No pending player requests.
            </p>
          ) : (
            <ul className="max-h-80 overflow-y-auto divide-y divide-gray-100">
              {requests.map((req) => {
                const u = req.from_user;
                const avatar = resolveImageUrl(u.profilePictureUrl) || DEFAULT_AVATAR;
                return (
                  <li
                    key={u.uid}
                    className="flex items-center gap-3 px-4 py-3"
                    data-testid={`notifications-request-${u.uid}`}
                  >
                    <Link to={`/players/${u.uid}`} onClick={() => setOpen(false)} className="flex-shrink-0">
                      <img
                        src={avatar}
                        alt={u.name || 'Player'}
                        className="w-10 h-10 rounded-full object-cover border-2 border-white shadow ring-2 ring-disc-green"
                      />
                    </Link>
                    <div className="flex-1 min-w-0">
                      <Link
                        to={`/players/${u.uid}`}
                        onClick={() => setOpen(false)}
                        className="font-semibold text-gray-800 hover:text-disc-green text-sm truncate block"
                      >
                        {u.name || 'Player'}
                      </Link>
                      <p className="text-xs text-gray-500">wants to add you as a player</p>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => handleAccept(u.uid)}
                        className="bg-disc-green hover:bg-disc-green/90 text-white text-xs font-bold px-2.5 py-1 rounded-md shadow-sm"
                        data-testid={`notifications-accept-${u.uid}`}
                        title="Add Player?"
                      >
                        ✓ Add
                      </button>
                      <button
                        type="button"
                        onClick={() => handleIgnore(u.uid)}
                        className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs font-bold px-2.5 py-1 rounded-md"
                        data-testid={`notifications-ignore-${u.uid}`}
                        title="Ignore"
                      >
                        ✕ Ignore
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <Link
            to="/likes"
            onClick={() => setOpen(false)}
            className="block text-center text-xs text-disc-green font-semibold px-4 py-3 border-t border-gray-100 hover:bg-disc-green/5"
            data-testid="notifications-view-all"
          >
            View all on Likes page →
          </Link>
        </div>
      )}
    </div>
  );
}
