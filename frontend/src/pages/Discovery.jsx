import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

/**
 * Discovery — scrollable multi-column grid of player cards.
 *
 * Whole card is clickable to /players/<uid> (the public profile view).
 * The Like + Friend buttons sit *above* that via z-index and stop the click
 * from propagating so they fire their own action instead of navigating.
 */
export default function Discovery() {
  const {
    deck,
    loading,
    deckHasMore,
    fetchDeck,
    loadMoreDeck,
    likePlayer,
    sendFriendRequest,
  } = useMatchStore();
  const navigate = useNavigate();
  const [toast, setToast] = useState(null);

  useEffect(() => {
    fetchDeck();
  }, [fetchDeck]);

  const flashToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast((curr) => (curr === msg ? null : curr)), 2200);
  };

  const handleLike = async (e, player) => {
    e.stopPropagation();
    e.preventDefault();
    await likePlayer(player);
    flashToast(`You liked ${player.name || 'them'} 💚`);
  };

  const handleFriend = async (e, player) => {
    e.stopPropagation();
    e.preventDefault();
    const res = await sendFriendRequest(player);
    if (res?.error) flashToast(`Friend request failed: ${res.error}`);
    else if (res?.friended) flashToast(`✅ You're now friends with ${player.name || 'them'} 🥏`);
    else flashToast(`✅ Friend request sent to ${player.name || 'them'}`);
  };

  const openProfile = (uid) => navigate(`/players/${uid}`);

  if (loading && deck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-loading">
        <p className="text-center text-gray-500">Loading players…</p>
      </div>
    );
  }

  if (deck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-empty">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-4">
            No more players to discover! 🎉
          </h2>
          <p className="text-gray-600">
            Check your <span className="font-semibold">Likes</span> tab to see who you
            matched with.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="discovery-view">
      <header className="mb-6 text-center">
        <h1 className="text-4xl font-bold text-disc-green mb-1">Find Your Ace Match</h1>
        <p className="text-gray-600">
          {deck.length} player{deck.length === 1 ? '' : 's'} to discover — tap a card to see their full profile
        </p>
      </header>

      {toast && (
        <div
          className="fixed top-20 left-1/2 -translate-x-1/2 bg-disc-green text-white px-5 py-2 rounded-full shadow-lg z-40 text-sm font-semibold"
          data-testid="discovery-toast"
        >
          {toast}
        </div>
      )}

      <div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"
        data-testid="discovery-grid"
      >
        {deck.map((player) => {
          const image = resolveImageUrl(player.profilePictureUrl) || DEFAULT_AVATAR;
          return (
            <article
              key={player.uid}
              role="button"
              tabIndex={0}
              onClick={() => openProfile(player.uid)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  openProfile(player.uid);
                }
              }}
              className="relative rounded-2xl overflow-hidden shadow-lg bg-gray-900 group flex flex-col cursor-pointer hover:shadow-xl hover:ring-2 hover:ring-disc-gold transition"
              data-testid={`discovery-card-${player.uid}`}
              aria-label={`Open ${player.name || 'player'}'s full profile`}
            >
              <div className="block relative" data-testid={`discovery-photo-${player.uid}`}>
                <img
                  src={image}
                  alt={player.name || 'Player'}
                  className="w-full h-72 object-cover group-hover:opacity-95 transition"
                  loading="lazy"
                />
                <div className="absolute top-0 left-0 right-0 bg-gradient-to-b from-black/80 via-black/30 to-transparent p-4 text-white pointer-events-none">
                  <h2 className="text-xl font-bold leading-tight">
                    {player.name}
                    {player.age ? `, ${player.age}` : ''}
                  </h2>
                  <p className="text-disc-gold text-sm font-semibold">{player.skillLevel}</p>
                </div>
              </div>

              <div className="p-4 bg-gray-900 text-white flex-1 flex flex-col">
                {player.bio && (
                  <p
                    className="text-sm text-white/90 mb-2 line-clamp-3"
                    data-testid={`discovery-bio-${player.uid}`}
                  >
                    {player.bio}
                  </p>
                )}

                {player.recent_post && (
                  <div
                    className="mb-3 bg-white/10 border border-white/15 rounded-lg px-3 py-2 text-xs"
                    data-testid={`discovery-recent-post-${player.uid}`}
                  >
                    <div className="flex items-center gap-2 uppercase tracking-wide text-white/60 mb-1">
                      <span>📣 Latest</span>
                      {player.recent_post.has_image && <span aria-hidden="true">📷</span>}
                    </div>
                    <p className="text-white/95 line-clamp-2">
                      {player.recent_post.body || '(photo only)'}
                    </p>
                  </div>
                )}

                <div className="text-xs space-y-0.5 mb-3 text-white/80">
                  {player.location && <p>📍 {player.location}</p>}
                  {player.favoriteCourse && <p>⛳ {player.favoriteCourse}</p>}
                  {player.homeCourse && <p>🏠 {player.homeCourse}</p>}
                  {player.favoriteFrisbee && <p>🥏 {player.favoriteFrisbee}</p>}
                </div>

                {player.interests && player.interests.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {player.interests.slice(0, 4).map((interest) => (
                      <span
                        key={interest}
                        className="bg-white/10 border border-white/15 text-white/90 px-2 py-0.5 rounded-full text-[10px]"
                      >
                        {interest}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-auto flex gap-2" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    onClick={(e) => handleLike(e, player)}
                    className="flex-1 bg-disc-gold hover:bg-disc-gold/90 text-white font-bold py-2 rounded-lg transition text-sm"
                    data-testid={`like-btn-${player.uid}`}
                  >
                    ❤️ Like
                  </button>
                  <button
                    type="button"
                    onClick={(e) => handleFriend(e, player)}
                    className="flex-1 bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 rounded-lg transition text-sm"
                    data-testid={`friend-btn-${player.uid}`}
                  >
                    🤝 Friend
                  </button>
                </div>

                <Link
                  to={`/players/${player.uid}`}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-3 text-center text-xs uppercase tracking-wider text-disc-gold/90 hover:text-disc-gold font-semibold"
                  data-testid={`discovery-view-profile-link-${player.uid}`}
                >
                  View full profile →
                </Link>
              </div>
            </article>
          );
        })}
      </div>

      {deckHasMore && (
        <div className="flex justify-center pt-8">
          <button
            type="button"
            onClick={loadMoreDeck}
            disabled={loading}
            className="border-2 border-disc-green text-disc-green hover:bg-disc-green hover:text-white font-semibold px-6 py-2 rounded-lg transition disabled:opacity-50"
            data-testid="discovery-load-more-btn"
          >
            {loading ? 'Loading…' : 'Load more players'}
          </button>
        </div>
      )}
    </div>
  );
}
