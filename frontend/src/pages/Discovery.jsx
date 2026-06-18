import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useMatchStore } from '../store/matchStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

const RADIUS_OPTIONS = [
  { label: 'Anywhere', value: null },
  { label: '10 mi', value: 10 },
  { label: '25 mi', value: 25 },
  { label: '50 mi', value: 50 },
  { label: '100 mi', value: 100 },
  { label: '250 mi', value: 250 },
];

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
    deckRadius,
    inbox,
    fetchDeck,
    loadMoreDeck,
    setDeckRadius,
    likePlayer,
    sendFriendRequest,
  } = useMatchStore();
  const navigate = useNavigate();
  const [toast, setToast] = useState(null);

  const sentSet = new Set(inbox?.sent_friend_request_uids || []);
  const friendSet = new Set(inbox?.friend_uids || []);
  const myLocation = useAuthStore((s) => s.profile?.location);
  const showLocationHint = !!deckRadius && !(myLocation && myLocation.trim());

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

  const radiusBar = (
    <div
      className="flex flex-wrap items-center justify-center gap-2 mb-5"
      data-testid="discovery-radius-bar"
    >
      <span className="text-sm font-semibold text-gray-700 mr-1">📍 Within:</span>
      {RADIUS_OPTIONS.map((opt) => {
        const active = (deckRadius ?? null) === opt.value;
        return (
          <button
            key={opt.label}
            type="button"
            onClick={() => setDeckRadius(opt.value)}
            className={
              active
                ? 'bg-disc-green text-white font-bold text-sm px-3 py-1.5 rounded-full shadow'
                : 'border border-disc-green text-disc-green hover:bg-disc-green/10 font-semibold text-sm px-3 py-1.5 rounded-full'
            }
            data-testid={`radius-option-${opt.value ?? 'any'}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );

  if (loading && deck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-loading">
        {radiusBar}
        <p className="text-center text-gray-500">Loading players…</p>
      </div>
    );
  }

  if (deck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-empty">
        {radiusBar}
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-4">
            {deckRadius
              ? `No players within ${deckRadius} miles 📍`
              : 'No more players to discover! 🎉'}
          </h2>
          <p className="text-gray-600">
            {deckRadius ? (
              <>
                Try widening your radius or set it to{' '}
                <button
                  type="button"
                  className="text-disc-green font-bold underline"
                  onClick={() => setDeckRadius(null)}
                  data-testid="discovery-reset-radius"
                >
                  Anywhere
                </button>
                .
              </>
            ) : (
              <>
                Check your <span className="font-semibold">Likes</span> tab to see who you matched with.
              </>
            )}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="discovery-view">
      <header className="mb-4 text-center">
        <h1 className="text-4xl font-bold text-disc-green mb-1">Find Your Ace Match</h1>
        <p className="text-gray-600 text-sm">
          {deck.length} player{deck.length === 1 ? '' : 's'} to discover — tap a card to view their full profile
        </p>
      </header>

      {radiusBar}

      {showLocationHint && (
        <div
          className="mb-5 max-w-xl mx-auto bg-disc-gold/15 border border-disc-gold/40 rounded-lg px-4 py-3 text-sm text-gray-800 flex items-start gap-2"
          data-testid="discovery-location-hint"
        >
          <span aria-hidden="true">📍</span>
          <p className="flex-1">
            <strong className="font-semibold">Set your location</strong> in{' '}
            <button
              type="button"
              className="text-disc-green font-bold underline"
              onClick={() => navigate('/profile')}
              data-testid="discovery-location-hint-cta"
            >
              your profile
            </button>{' '}
            so distance filtering can find players actually near you.
          </p>
        </div>
      )}

      {toast && (
        <div
          className="fixed top-20 left-1/2 -translate-x-1/2 bg-disc-green text-white px-5 py-2 rounded-full shadow-lg z-40 text-sm font-semibold"
          data-testid="discovery-toast"
        >
          {toast}
        </div>
      )}

      <div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
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
              className="relative bg-white rounded-2xl shadow-sm hover:shadow-md hover:ring-2 hover:ring-disc-green/60 transition cursor-pointer overflow-hidden flex flex-col"
              data-testid={`discovery-card-${player.uid}`}
              aria-label={`Open ${player.name || 'player'}'s full profile`}
            >
              {/* Compact information box */}
              <div className="px-3 pt-3 pb-1 text-xs text-gray-700 leading-snug">
                <h2 className="text-base font-bold text-disc-green leading-tight truncate">
                  {player.name || 'Player'}
                  {player.age ? `, ${player.age}` : ''}
                </h2>
                {player.skillLevel && (
                  <p className="text-[10px] uppercase tracking-wide text-disc-gold font-bold mt-0.5">
                    {player.skillLevel}
                  </p>
                )}
                {player.bio && (
                  <p
                    className="text-[12px] text-gray-700 line-clamp-2 mt-1"
                    data-testid={`discovery-bio-${player.uid}`}
                  >
                    {player.bio}
                  </p>
                )}
                <ul className="text-[11px] text-gray-600 mt-1 space-y-px">
                  {player.location && (
                    <li className="truncate">
                      📍 {player.location}
                      {typeof player.distance_miles === 'number' && (
                        <span
                          className="ml-1 text-disc-green font-semibold"
                          data-testid={`discovery-distance-${player.uid}`}
                        >
                          · {player.distance_miles} mi away
                        </span>
                      )}
                    </li>
                  )}
                  {player.favoriteCourse && (
                    <li className="truncate">⛳ {player.favoriteCourse}</li>
                  )}
                  {player.homeCourse && (
                    <li className="truncate">🏠 {player.homeCourse}</li>
                  )}
                  {player.favoriteFrisbee && (
                    <li className="truncate">🥏 {player.favoriteFrisbee}</li>
                  )}
                </ul>
                {player.interests && player.interests.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {player.interests.slice(0, 4).map((interest) => (
                      <span
                        key={interest}
                        className="bg-disc-green/10 border border-disc-green/30 text-disc-green px-1.5 py-px rounded-full text-[9px] font-medium"
                      >
                        {interest}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Avatar circle (lower-left) + action row */}
              <div className="px-3 pb-3 pt-1 flex items-end justify-between gap-2">
                <img
                  src={image}
                  alt={player.name || 'Player'}
                  className="w-16 h-16 rounded-full object-cover border-2 border-white shadow ring-2 ring-disc-green flex-shrink-0"
                  loading="lazy"
                  data-testid={`discovery-avatar-${player.uid}`}
                />
                <div
                  className="flex flex-wrap gap-x-3 gap-y-1 flex-1 justify-end items-center"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    onClick={(e) => handleNice(e, player)}
                    className="text-disc-green hover:text-disc-green/80 font-semibold text-sm flex items-center gap-1"
                    data-testid={`nice-btn-${player.uid}`}
                    title="Nice"
                  >
                    👍 Nice
                  </button>
                  <button
                    type="button"
                    onClick={(e) => handleMessage(e, player)}
                    className="text-disc-green hover:text-disc-green/80 font-semibold text-sm flex items-center gap-1"
                    data-testid={`message-btn-${player.uid}`}
                    title="Message"
                  >
                    💬 Message
                  </button>
                  {isFriend ? (
                    <span
                      className="text-emerald-600 font-semibold text-sm flex items-center gap-1"
                      data-testid={`player-status-friends-${player.uid}`}
                      title="You are players"
                    >
                      ✓ Players
                    </span>
                  ) : sent ? (
                    <span
                      className="text-gray-500 font-semibold text-sm flex items-center gap-1"
                      data-testid={`player-status-sent-${player.uid}`}
                      title="Player request sent"
                    >
                      ⏳ Sent
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => handlePlayer(e, player)}
                      className="text-disc-green hover:text-disc-green/80 font-semibold text-sm flex items-center gap-1"
                      data-testid={`player-btn-${player.uid}`}
                      title="Send player request"
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
