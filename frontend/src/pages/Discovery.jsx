import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

/**
 * Discovery — compact picture-first grid.
 *
 * Each card is mostly a profile photo with the name/age overlaid and two
 * tiny action buttons. The whole card is clickable -> /players/<uid>.
 * Players stay on the deck after "Player" (friend request) until they
 * become real friends, so users don't lose track of who they pinged.
 */
export default function Discovery() {
  const {
    deck,
    loading,
    deckHasMore,
    inbox,
    fetchDeck,
    loadMoreDeck,
    likePlayer,
    sendFriendRequest,
  } = useMatchStore();
  const navigate = useNavigate();
  const [toast, setToast] = useState(null);

  const sentSet = new Set(inbox?.sent_friend_request_uids || []);
  const friendSet = new Set(inbox?.friend_uids || []);

  useEffect(() => {
    fetchDeck();
  }, [fetchDeck]);

  const flashToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast((curr) => (curr === msg ? null : curr)), 2200);
  };

  const handleNice = async (e, player) => {
    e.stopPropagation();
    e.preventDefault();
    await likePlayer(player);
    flashToast(`Nice — you tagged ${player.name || 'them'} 💚`);
  };

  const handlePlayer = async (e, player) => {
    e.stopPropagation();
    e.preventDefault();
    const res = await sendFriendRequest(player);
    if (res?.error) flashToast(`Request failed: ${res.error}`);
    else if (res?.friended) flashToast(`✅ You're now players with ${player.name || 'them'} 🥏`);
    else flashToast(`✅ Player request sent to ${player.name || 'them'}`);
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
          <h2 className="text-3xl font-bold text-gray-800 mb-4">No more players to discover! 🎉</h2>
          <p className="text-gray-600">
            Check your <span className="font-semibold">Likes</span> tab to see who you matched with.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="discovery-view">
      <header className="mb-6 text-center">
        <h1 className="text-4xl font-bold text-disc-green mb-1">Find Your Ace Match</h1>
        <p className="text-gray-600 text-sm">
          {deck.length} player{deck.length === 1 ? '' : 's'} to discover — tap a card to view their full profile
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
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4"
        data-testid="discovery-grid"
      >
        {deck.map((player) => {
          const image = resolveImageUrl(player.profilePictureUrl) || DEFAULT_AVATAR;
          const isFriend = friendSet.has(player.uid);
          const sent = sentSet.has(player.uid);
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
              className="relative rounded-xl overflow-hidden shadow-md bg-gray-900 cursor-pointer hover:shadow-xl hover:ring-2 hover:ring-disc-gold transition aspect-[3/4] flex flex-col"
              data-testid={`discovery-card-${player.uid}`}
              aria-label={`Open ${player.name || 'player'}'s full profile`}
            >
              <img
                src={image}
                alt={player.name || 'Player'}
                className="absolute inset-0 w-full h-full object-cover"
                loading="lazy"
              />
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black via-black/60 to-transparent p-3 text-white">
                <h2 className="text-base font-bold leading-tight truncate">
                  {player.name}
                  {player.age ? `, ${player.age}` : ''}
                </h2>
                {player.skillLevel && (
                  <p className="text-disc-gold text-[11px] font-semibold truncate">
                    {player.skillLevel}
                  </p>
                )}
                <div
                  className="mt-2 flex gap-1.5"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    onClick={(e) => handleNice(e, player)}
                    className="flex-1 bg-disc-gold/95 hover:bg-disc-gold text-white text-[11px] font-bold py-1 rounded-md transition"
                    data-testid={`nice-btn-${player.uid}`}
                    aria-label={`Mark ${player.name || 'player'} as nice`}
                  >
                    👍 Nice
                  </button>
                  {isFriend ? (
                    <span
                      className="flex-1 bg-emerald-700/90 text-white text-[11px] font-bold py-1 rounded-md text-center"
                      data-testid={`player-status-friends-${player.uid}`}
                    >
                      ✓ Player
                    </span>
                  ) : sent ? (
                    <span
                      className="flex-1 bg-gray-500/90 text-white text-[11px] font-bold py-1 rounded-md text-center"
                      data-testid={`player-status-sent-${player.uid}`}
                    >
                      ⏳ Sent
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => handlePlayer(e, player)}
                      className="flex-1 bg-disc-green/95 hover:bg-disc-green text-white text-[11px] font-bold py-1 rounded-md transition"
                      data-testid={`player-btn-${player.uid}`}
                    >
                      🤝 Player
                    </button>
                  )}
                </div>
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
