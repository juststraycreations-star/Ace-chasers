import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

/**
 * Discovery — info-box cards with a small circular avatar tucked into the
 * lower-left corner. Shows every non-private field the API returns so
 * players get a real sense of someone before they tap into the full
 * profile. Three-action bar at the bottom: Nice / Player request / Message.
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

  const handleMessage = (e, player) => {
    e.stopPropagation();
    e.preventDefault();
    navigate('/messages', { state: { withUid: player.uid, name: player.name } });
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
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
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
              className="relative bg-white rounded-2xl shadow-md hover:shadow-xl hover:ring-2 hover:ring-disc-green transition cursor-pointer overflow-hidden flex flex-col"
              data-testid={`discovery-card-${player.uid}`}
              aria-label={`Open ${player.name || 'player'}'s full profile`}
            >
              {/* Information box */}
              <div className="px-4 pt-4 pb-2 text-sm text-gray-700 space-y-1 min-h-[180px]">
                <h2 className="text-lg font-bold text-disc-green leading-tight">
                  {player.name || 'Player'}
                  {player.age ? `, ${player.age}` : ''}
                </h2>
                {player.skillLevel && (
                  <p className="text-xs uppercase tracking-wide text-disc-gold font-semibold">
                    {player.skillLevel}
                  </p>
                )}
                {player.bio && (
                  <p
                    className="text-sm text-gray-700 line-clamp-3 pt-1"
                    data-testid={`discovery-bio-${player.uid}`}
                  >
                    {player.bio}
                  </p>
                )}
                <ul className="text-xs text-gray-600 space-y-0.5 pt-1">
                  {player.location && <li>📍 {player.location}</li>}
                  {player.favoriteCourse && <li>⛳ Fav course: {player.favoriteCourse}</li>}
                  {player.homeCourse && <li>🏠 Home course: {player.homeCourse}</li>}
                  {player.favoriteFrisbee && <li>🥏 Fav frisbee: {player.favoriteFrisbee}</li>}
                </ul>
                {player.interests && player.interests.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {player.interests.slice(0, 5).map((interest) => (
                      <span
                        key={interest}
                        className="bg-disc-green/10 border border-disc-green/30 text-disc-green px-2 py-0.5 rounded-full text-[10px] font-medium"
                      >
                        {interest}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Avatar circle, lower-left */}
              <div className="px-4 pb-3 flex items-end justify-between gap-2">
                <img
                  src={image}
                  alt={player.name || 'Player'}
                  className="w-14 h-14 rounded-full object-cover border-2 border-white shadow ring-2 ring-disc-green/30 flex-shrink-0"
                  loading="lazy"
                  data-testid={`discovery-avatar-${player.uid}`}
                />
                <div
                  className="flex gap-1.5 flex-1 justify-end"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    onClick={(e) => handleNice(e, player)}
                    className="bg-disc-gold/95 hover:bg-disc-gold text-white text-[11px] font-bold py-1.5 px-2.5 rounded-md transition"
                    data-testid={`nice-btn-${player.uid}`}
                    aria-label={`Mark ${player.name || 'player'} as nice`}
                    title="Nice"
                  >
                    👍
                  </button>
                  {isFriend ? (
                    <button
                      type="button"
                      onClick={(e) => handleMessage(e, player)}
                      className="bg-disc-green hover:bg-disc-green/90 text-white text-[11px] font-bold py-1.5 px-2.5 rounded-md transition"
                      data-testid={`message-btn-${player.uid}`}
                      title="Message"
                    >
                      💬
                    </button>
                  ) : sent ? (
                    <span
                      className="bg-gray-500/90 text-white text-[11px] font-bold py-1.5 px-2.5 rounded-md text-center"
                      data-testid={`player-status-sent-${player.uid}`}
                      title="Player request sent"
                    >
                      ⏳
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => handlePlayer(e, player)}
                      className="bg-disc-green/95 hover:bg-disc-green text-white text-[11px] font-bold py-1.5 px-2.5 rounded-md transition"
                      data-testid={`player-btn-${player.uid}`}
                      title="Send player request"
                    >
                      🤝
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
