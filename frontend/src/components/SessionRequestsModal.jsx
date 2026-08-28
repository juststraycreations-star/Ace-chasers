import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

// We only ever show this modal once per session — picks back up after a hard
// browser refresh / re-login. sessionStorage (not localStorage) on purpose.
const SHOWN_KEY = 'ace_friend_requests_session_modal_shown';

/**
 * SessionRequestsModal
 *
 * The first time the user has pending player requests after auth-ready in a
 * fresh session, prompt them with an Add Player? / Ignore for each one in a
 * blocking modal. Subsequent toasts are handled by NotificationsBell.
 */
export default function SessionRequestsModal() {
  const inbox = useMatchStore((s) => s.inbox);
  const acceptFriendRequest = useMatchStore((s) => s.acceptFriendRequest);
  const declineFriendRequest = useMatchStore((s) => s.declineFriendRequest);

  const requests = inbox?.incoming_friend_requests || [];
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (requests.length === 0) return;
    let alreadyShown;
    try {
      alreadyShown = sessionStorage.getItem(SHOWN_KEY) === '1';
    } catch (_e) {
      alreadyShown = false;
    }
    if (alreadyShown) return;
    setOpen(true);
    try {
      sessionStorage.setItem(SHOWN_KEY, '1');
    } catch (_e) {
      /* sessionStorage may be disabled; the only consequence is that the
         modal could reappear after navigation. Acceptable fallback. */
    }
  }, [requests.length]);

  if (!open || requests.length === 0) return null;

  const close = () => setOpen(false);

  const handleAccept = async (uid) => {
    await acceptFriendRequest(uid);
  };

  const handleIgnore = async (uid) => {
    await declineFriendRequest(uid);
  };

  return (
    <div
      className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4"
      onClick={close}
      data-testid="session-requests-overlay"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        data-testid="session-requests-modal"
      >
        <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-bold text-disc-green">
            Add Player? {requests.length > 1 ? `(${requests.length})` : ''}
          </h2>
          <button
            type="button"
            onClick={close}
            className="text-gray-500 hover:text-gray-800 font-bold text-xl leading-none"
            aria-label="Close"
            data-testid="session-requests-close"
          >
            ✕
          </button>
        </div>

        <p className="px-5 py-3 text-sm text-gray-600">
          {requests.length === 1
            ? 'A player wants to add you. Want to add them back?'
            : `${requests.length} players want to add you. Add or ignore each one below.`}
        </p>

        <ul className="overflow-y-auto divide-y divide-gray-100">
          {requests.map((req) => {
            const u = req.from_user;
            const avatar = resolveImageUrl(u.profilePictureUrl) || DEFAULT_AVATAR;
            return (
              <li
                key={u.uid}
                className="flex items-center gap-3 px-5 py-3"
                data-testid={`session-request-${u.uid}`}
              >
                <Link to={`/players/${u.uid}`} onClick={close} className="flex-shrink-0">
                  <img
                    src={avatar}
                    alt={u.name || 'Player'}
                    className="w-12 h-12 rounded-full object-cover border-2 border-white shadow ring-2 ring-disc-green"
                  />
                </Link>
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/players/${u.uid}`}
                    onClick={close}
                    className="font-bold text-gray-800 hover:text-disc-green truncate block"
                  >
                    {u.name || 'Player'}
                  </Link>
                  <p className="text-xs text-gray-500">wants to add you as a player</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => handleAccept(u.uid)}
                    className="bg-disc-green hover:bg-disc-green/90 text-white text-sm font-bold px-3 py-1.5 rounded-lg shadow-sm"
                    data-testid={`session-accept-${u.uid}`}
                  >
                    ✓ Add
                  </button>
                  <button
                    type="button"
                    onClick={() => handleIgnore(u.uid)}
                    className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm font-bold px-3 py-1.5 rounded-lg"
                    data-testid={`session-ignore-${u.uid}`}
                  >
                    ✕ Ignore
                  </button>
                </div>
              </li>
            );
          })}
        </ul>

        <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between">
          <Link
            to="/likes"
            onClick={close}
            className="text-xs text-disc-green font-semibold hover:underline"
            data-testid="session-requests-view-all"
          >
            View all on Likes page →
          </Link>
          <button
            type="button"
            onClick={close}
            className="text-sm text-gray-600 hover:text-gray-900 font-semibold"
            data-testid="session-requests-later"
          >
            Decide later
          </button>
        </div>
      </div>
    </div>
  );
}
