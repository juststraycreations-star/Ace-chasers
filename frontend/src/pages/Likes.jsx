import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

/**
 * Likes page — three sections:
 *   1. Pending friend requests received (Accept / Decline buttons)
 *   2. People who liked you (just a notification list)
 *   3. People you liked (existing outgoing list, with Add Friend on mutual matches)
 */
export default function Likes() {
  const {
    likes,
    inbox,
    loading,
    fetchLikes,
    fetchInbox,
    addFriend,
    removeLike,
    acceptFriendRequest,
    declineFriendRequest,
    sendFriendRequest,
  } = useMatchStore();

  useEffect(() => {
    fetchLikes();
    fetchInbox();
  }, [fetchLikes, fetchInbox]);

  const incomingLikes = inbox?.incoming_likes || [];
  const friendRequests = inbox?.incoming_friend_requests || [];
  const matchCount = likes.filter((l) => l.matched).length;
  const isEmpty =
    likes.length === 0 && incomingLikes.length === 0 && friendRequests.length === 0;

  if (loading && isEmpty) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12" data-testid="likes-loading">
        <p className="text-center text-gray-500">Loading your likes…</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12" data-testid="likes-view">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-disc-green mb-2">Your Likes</h1>
        <p className="text-gray-600">
          {likes.length} liked profile{likes.length === 1 ? '' : 's'} ·{' '}
          <span className="text-disc-gold font-semibold">
            {matchCount} mutual match{matchCount === 1 ? '' : 'es'}
          </span>
          {friendRequests.length > 0 && (
            <>
              {' · '}
              <span className="text-disc-green font-semibold">
                {friendRequests.length} friend request
                {friendRequests.length === 1 ? '' : 's'}
              </span>
            </>
          )}
        </p>
      </div>

      {/* ===== Pending Friend Requests ===== */}
      {friendRequests.length > 0 && (
        <section className="mb-10" data-testid="friend-requests-section">
          <h2 className="text-xl font-bold text-gray-800 mb-3">
            🤝 Friend requests <span className="text-disc-green">({friendRequests.length})</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {friendRequests.map(({ from_user: u }) => (
              <div
                key={u.uid}
                className="bg-white rounded-2xl shadow flex items-center gap-3 p-3"
                data-testid={`friend-request-${u.uid}`}
              >
                <Link
                  to={`/players/${u.uid}`}
                  className="flex-shrink-0"
                  aria-label={`Open ${u.name || 'player'}'s profile`}
                >
                  <img
                    src={resolveImageUrl(u.profilePictureUrl) || DEFAULT_AVATAR}
                    alt={u.name || 'Player'}
                    className="w-14 h-14 rounded-full object-cover"
                  />
                </Link>
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/players/${u.uid}`}
                    className="font-semibold text-gray-800 hover:text-disc-green block truncate"
                  >
                    {u.name || 'Player'}
                  </Link>
                  <p className="text-xs text-gray-500 truncate">
                    wants to be your friend
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => acceptFriendRequest(u.uid)}
                    className="bg-disc-green hover:bg-disc-green/90 text-white text-xs font-bold px-3 py-2 rounded-lg"
                    data-testid={`accept-friend-${u.uid}`}
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    onClick={() => declineFriendRequest(u.uid)}
                    className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs font-bold px-3 py-2 rounded-lg"
                    data-testid={`decline-friend-${u.uid}`}
                  >
                    Decline
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ===== Incoming Likes (notification list) ===== */}
      {incomingLikes.length > 0 && (
        <section className="mb-10" data-testid="incoming-likes-section">
          <h2 className="text-xl font-bold text-gray-800 mb-3">
            ❤️ People who liked you{' '}
            <span className="text-disc-gold">({incomingLikes.length})</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {incomingLikes.map(({ from_user: u }) => (
              <div
                key={u.uid}
                className="bg-white rounded-2xl shadow flex items-center gap-3 p-3"
                data-testid={`incoming-like-${u.uid}`}
              >
                <Link
                  to={`/players/${u.uid}`}
                  className="flex-shrink-0"
                  aria-label={`Open ${u.name || 'player'}'s profile`}
                >
                  <img
                    src={resolveImageUrl(u.profilePictureUrl) || DEFAULT_AVATAR}
                    alt={u.name || 'Player'}
                    className="w-14 h-14 rounded-full object-cover"
                  />
                </Link>
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/players/${u.uid}`}
                    className="font-semibold text-gray-800 hover:text-disc-green block truncate"
                  >
                    {u.name || 'Player'}
                  </Link>
                  <p className="text-xs text-gray-500 truncate">liked your profile</p>
                </div>
                <button
                  type="button"
                  onClick={() => sendFriendRequest(u)}
                  className="bg-disc-green hover:bg-disc-green/90 text-white text-xs font-bold px-3 py-2 rounded-lg"
                  data-testid={`send-friend-from-like-${u.uid}`}
                  title="Send a friend request"
                >
                  🤝 Friend
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ===== Outgoing Likes (existing list) ===== */}
      <section data-testid="outgoing-likes-section">
        <h2 className="text-xl font-bold text-gray-800 mb-3">
          💚 Profiles you liked{' '}
          {likes.length > 0 && <span className="text-disc-green">({likes.length})</span>}
        </h2>

        {likes.length === 0 ? (
          <div
            className="bg-white rounded-xl shadow p-12 text-center"
            data-testid="likes-empty"
          >
            <p className="text-gray-500 text-lg">
              You haven&apos;t liked anyone yet. Head to{' '}
              <span className="font-semibold text-disc-green">Discovery</span> and tap ❤️ on
              a profile to get started.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {likes.map(({ player, matched, friended }) => (
              <div
                key={player.uid}
                className="bg-white rounded-2xl shadow-lg overflow-hidden flex flex-col"
                data-testid={`liked-player-${player.uid}`}
              >
                <Link
                  to={`/players/${player.uid}`}
                  className="relative h-56 bg-gray-300 block"
                  aria-label={`Open ${player.name || 'player'}'s profile`}
                  data-testid={`liked-player-link-${player.uid}`}
                >
                  <img
                    src={resolveImageUrl(player.profilePictureUrl) || DEFAULT_AVATAR}
                    alt={player.name}
                    className="w-full h-full object-cover hover:opacity-95 transition"
                  />
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black via-transparent to-transparent p-4">
                    <h2 className="text-2xl font-bold text-white">
                      {player.name}
                      {player.age ? `, ${player.age}` : ''}
                    </h2>
                    <p className="text-disc-gold text-sm">{player.skillLevel}</p>
                  </div>
                  {matched && (
                    <div
                      className="absolute top-3 right-3 bg-disc-gold text-white text-xs font-bold uppercase px-3 py-1 rounded-full shadow"
                      data-testid={`match-badge-${player.uid}`}
                    >
                      It&apos;s a match!
                    </div>
                  )}
                </Link>

                <div className="p-4 flex-1 flex flex-col">
                  <div className="text-sm text-gray-600 space-y-1 mb-4">
                    {player.location && (
                      <p>
                        <span className="font-semibold text-gray-800">Location:</span>{' '}
                        {player.location}
                      </p>
                    )}
                    {player.favoriteFrisbee && (
                      <p>
                        <span className="font-semibold text-gray-800">Favorite Frisbee:</span>{' '}
                        {player.favoriteFrisbee}
                      </p>
                    )}
                  </div>

                  <div className="mt-auto flex items-center justify-between gap-2">
                    {matched ? (
                      friended ? (
                        <span
                          className="text-disc-green font-semibold text-sm"
                          data-testid={`friended-label-${player.uid}`}
                        >
                          ✓ Friend added
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => addFriend(player.uid)}
                          className="text-disc-green hover:text-disc-green/80 font-semibold text-sm underline underline-offset-2"
                          data-testid={`add-friend-link-${player.uid}`}
                        >
                          + Add friend
                        </button>
                      )
                    ) : (
                      <span className="text-gray-400 text-sm italic">
                        Waiting for them to like back…
                      </span>
                    )}

                    <button
                      type="button"
                      onClick={() => removeLike(player.uid)}
                      className="text-xs text-gray-400 hover:text-red-500 transition"
                      data-testid={`unlike-btn-${player.uid}`}
                    >
                      Unlike
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
