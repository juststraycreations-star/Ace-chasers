import { useEffect } from 'react';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';

const DEFAULT_AVATAR =
  'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&h=1000&fit=crop';

/**
 * Discovery page — a vertically scrollable feed of player cards.
 * Each card uses the player's profile picture as a full-bleed background;
 * their bio and the rest of their public profile sits on top of the photo
 * inside a darkened gradient panel for legibility.
 */
export default function Discovery() {
  const { deck, loading, fetchDeck, likePlayer, passPlayer } = useMatchStore();

  useEffect(() => {
    fetchDeck();
  }, [fetchDeck]);

  if (loading && deck.length === 0) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12" data-testid="discovery-loading">
        <p className="text-center text-gray-500">Loading players…</p>
      </div>
    );
  }

  if (deck.length === 0) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12" data-testid="discovery-empty">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-4">
            No more players to discover! 🎉
          </h2>
          <p className="text-gray-600">
            Check your <span className="font-semibold">Likes</span> tab to see who you matched with.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8" data-testid="discovery-view">
      <header className="mb-6 text-center">
        <h1 className="text-4xl font-bold text-disc-green mb-1">Find Your Ace Match</h1>
        <p className="text-gray-600">
          {deck.length} player{deck.length === 1 ? '' : 's'} to discover — scroll to browse, tap ❤️ to like
        </p>
      </header>

      <div className="space-y-6">
        {deck.map((player) => {
          const image = resolveImageUrl(player.profilePictureUrl) || DEFAULT_AVATAR;
          return (
            <article
              key={player.uid}
              className="relative rounded-3xl overflow-hidden shadow-xl bg-gray-900 group"
              data-testid={`discovery-card-${player.uid}`}
            >
              {/* Full-bleed profile image */}
              <img
                src={image}
                alt={player.name || 'Player'}
                className="w-full h-[640px] object-cover"
                loading="lazy"
              />

              {/* Top-of-card identity (subtle gradient so name reads on any photo) */}
              <div className="absolute top-0 left-0 right-0 bg-gradient-to-b from-black/70 via-black/30 to-transparent p-6 text-white pointer-events-none">
                <h2 className="text-3xl font-bold">
                  {player.name}
                  {player.age ? `, ${player.age}` : ''}
                </h2>
                <p className="text-disc-gold font-semibold">{player.skillLevel}</p>
              </div>

              {/* Bio + shared profile content overlay (bottom) */}
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/70 to-transparent p-6 pt-20 text-white">
                {player.bio && (
                  <p
                    className="text-base leading-relaxed mb-3"
                    data-testid={`discovery-bio-${player.uid}`}
                  >
                    {player.bio}
                  </p>
                )}

                <div className="text-sm space-y-1 mb-3 text-white/85">
                  {player.location && (
                    <p>
                      <span className="font-semibold">📍 Location:</span> {player.location}
                    </p>
                  )}
                  {player.favoriteCourse && (
                    <p>
                      <span className="font-semibold">⛳ Favorite Course:</span> {player.favoriteCourse}
                    </p>
                  )}
                  {player.favoriteFrisbee && (
                    <p>
                      <span className="font-semibold">🥏 Favorite Frisbee:</span> {player.favoriteFrisbee}
                    </p>
                  )}
                </div>

                {player.interests && player.interests.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-4">
                    {player.interests.map((interest) => (
                      <span
                        key={interest}
                        className="bg-white/15 backdrop-blur-sm border border-white/20 text-white px-3 py-1 rounded-full text-xs"
                      >
                        {interest}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => passPlayer(player)}
                    className="flex-1 bg-white/20 hover:bg-white/30 backdrop-blur-sm border border-white/30 text-white font-bold py-3 rounded-xl transition"
                    data-testid={`pass-btn-${player.uid}`}
                  >
                    ✕ Pass
                  </button>
                  <button
                    type="button"
                    onClick={() => likePlayer(player)}
                    className="flex-1 bg-disc-gold hover:bg-disc-gold/90 text-white font-bold py-3 rounded-xl transition shadow-lg"
                    data-testid={`like-btn-${player.uid}`}
                  >
                    ❤️ Like
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
