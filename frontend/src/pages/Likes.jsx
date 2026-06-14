import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';

/**
 * Likes page - shows the profiles the user has liked.
 * If a like is matched (mutual), an "Add Friend" link is surfaced.
 */
export default function Likes() {
  const { likes, loading, fetchLikes, addFriend, removeLike } = useMatchStore();

  useEffect(() => {
    fetchLikes();
  }, [fetchLikes]);

  if (loading && likes.length === 0) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12" data-testid="likes-loading">
        <p className="text-center text-gray-500">Loading your likes…</p>
      </div>
    );
  }

  if (likes.length === 0) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12" data-testid="likes-empty">
        <h1 className="text-4xl font-bold text-disc-green mb-2">Your Likes</h1>
        <p className="text-gray-600 mb-8">Profiles you&apos;ve liked will show up here.</p>
        <div className="bg-white rounded-xl shadow p-12 text-center">
          <p className="text-gray-500 text-lg">
            You haven&apos;t liked anyone yet. Head to{' '}
            <span className="font-semibold text-disc-green">Discovery</span> and tap ❤️ on a profile
            to get started.
          </p>
        </div>
      </div>
    );
  }

  const matchCount = likes.filter((l) => l.matched).length;

  return (
    <div className="max-w-4xl mx-auto px-4 py-12" data-testid="likes-view">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-disc-green mb-2">Your Likes</h1>
        <p className="text-gray-600">
          {likes.length} liked profile{likes.length === 1 ? '' : 's'}.{' '}
          <span className="text-disc-gold font-semibold">
            {matchCount} mutual match{matchCount === 1 ? '' : 'es'}.
          </span>
        </p>
      </div>

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
                src={player.profilePictureUrl}
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
                    <span className="font-semibold text-gray-800">Location:</span> {player.location}
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
                  <span className="text-gray-400 text-sm italic">Waiting for them to like back…</span>
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
    </div>
  );
}
