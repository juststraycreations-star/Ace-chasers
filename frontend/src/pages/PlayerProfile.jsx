import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import PublicProfilePreview from '../components/PublicProfilePreview';

/**
 * Public read-only view of any user's profile, reached via /players/:uid.
 * Shows a Message button + the player's friends list at the bottom.
 */
export default function PlayerProfile() {
  const { uid } = useParams();
  const navigate = useNavigate();
  const inbox = useMatchStore((s) => s.inbox);
  const sendFriendRequest = useMatchStore((s) => s.sendFriendRequest);
  const [profile, setProfile] = useState(null);
  const [theirFriends, setTheirFriends] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState('');

  const isFriend = (inbox?.friend_uids || []).includes(uid);
  const requestSent = (inbox?.sent_friend_request_uids || []).includes(uid);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [pRes, fRes] = await Promise.all([
          api.get(`/users/${uid}`),
          api.get(`/users/${uid}/friends`).catch(() => ({ data: [] })),
        ]);
        if (!cancelled) {
          setProfile(pRes.data);
          setTheirFriends(fRes.data || []);
        }
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [uid]);

  const handleMessage = () => {
    // Messages page doesn't currently support deep-linking to a thread,
    // so for now we just take the user there with the target uid in state.
    navigate('/messages', { state: { withUid: uid, name: profile?.name } });
  };

  const handleAddPlayer = async () => {
    if (!profile) return;
    const res = await sendFriendRequest(profile);
    if (res?.friended) setActionMsg('✅ You are now players!');
    else if (res?.error) setActionMsg(`Failed: ${res.error}`);
    else setActionMsg('✅ Player request sent');
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8" data-testid="player-profile-view">
      <Link
        to="/discovery"
        className="text-sm text-disc-green hover:underline mb-4 inline-block"
        data-testid="player-profile-back"
      >
        ← Back to Discovery
      </Link>

      {loading ? (
        <p className="text-center text-gray-500" data-testid="player-profile-loading">
          Loading profile…
        </p>
      ) : error ? (
        <div
          className="bg-red-50 border-2 border-red-300 text-red-800 rounded-lg p-4"
          data-testid="player-profile-error"
        >
          {error}
        </div>
      ) : profile ? (
        <>
          <PublicProfilePreview player={profile} />

          {/* Action buttons */}
          <div
            className="mt-4 flex flex-wrap gap-2"
            data-testid="player-profile-actions"
          >
            {isFriend ? (
              <button
                type="button"
                onClick={handleMessage}
                className="flex-1 bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 px-4 rounded-lg transition"
                data-testid="player-profile-message-btn"
              >
                💬 Message
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleAddPlayer}
                  disabled={requestSent}
                  className="flex-1 bg-disc-green hover:bg-disc-green/90 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded-lg transition"
                  data-testid="player-profile-add-btn"
                >
                  {requestSent ? '⏳ Request Sent' : '🤝 Add Player'}
                </button>
                <p className="w-full text-xs text-gray-500 italic">
                  Become players to send messages and see Players-only posts.
                </p>
              </>
            )}
          </div>
          {actionMsg && (
            <p
              className="mt-2 text-sm text-disc-green font-semibold"
              data-testid="player-profile-action-msg"
            >
              {actionMsg}
            </p>
          )}

          {/* Their friends section */}
          {theirFriends.length > 0 && (
            <section
              className="mt-6 bg-white rounded-2xl shadow p-5"
              data-testid="player-profile-friends-section"
            >
              <h3 className="text-lg font-bold text-disc-green mb-3">
                🥏 {profile.name?.split(' ')[0] || 'Their'} Players
                <span className="ml-2 text-sm text-gray-500 font-normal">
                  ({theirFriends.length})
                </span>
              </h3>
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                {theirFriends.slice(0, 12).map((f) => (
                  <Link
                    key={f.uid}
                    to={`/players/${f.uid}`}
                    className="flex flex-col items-center group"
                    data-testid={`player-profile-friend-${f.uid}`}
                  >
                    <img
                      src={resolveImageUrl(f.profilePictureUrl) || DEFAULT_AVATAR}
                      alt={f.name || 'Player'}
                      className="w-14 h-14 rounded-full object-cover mb-1 group-hover:ring-2 group-hover:ring-disc-green transition"
                    />
                    <span className="text-xs font-semibold text-gray-700 text-center truncate w-full">
                      {f.name || 'Player'}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </>
      ) : null}
    </div>
  );
}
