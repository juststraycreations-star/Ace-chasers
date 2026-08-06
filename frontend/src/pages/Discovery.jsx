import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useMatchStore } from '../store/matchStore';
import { DISCOVERY_INTEREST_OPTIONS } from '../lib/interestTags';
import DismissibleBanner from '../components/DismissibleBanner';
import PublicProfilePreview from '../components/PublicProfilePreview';
import MessageComposeModal from '../components/MessageComposeModal';
import { PlayerGridSkeleton } from '../components/Skeletons';

const RADIUS_OPTIONS = [
  { label: 'Anywhere', value: null },
  { label: '10 mi', value: 10 },
  { label: '25 mi', value: 25 },
  { label: '50 mi', value: 50 },
  { label: '100 mi', value: 100 },
  { label: '250 mi', value: 250 },
];

const INTEREST_OPTIONS = DISCOVERY_INTEREST_OPTIONS;

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
    error,
    deckHasMore,
    deckRadius,
    deckInterestedIn,
    inbox,
    fetchDeck,
    loadMoreDeck,
    setDeckRadius,
    setDeckInterestedIn,
    likePlayer,
    sendFriendRequest,
  } = useMatchStore();
  const navigate = useNavigate();
  const [toast, setToast] = useState(null);
  const [composeRecipient, setComposeRecipient] = useState(null);
  const [autoRetryCount, setAutoRetryCount] = useState(0);

  // Defensive: every store field these depend on may be null/undefined on
  // the first mount, or become so if the response payload is malformed.
  // Fall back to empty structures so downstream JSX never crashes.
  const safeDeck = Array.isArray(deck) ? deck : [];
  const safeInbox = inbox || {};
  const sentSet = new Set(safeInbox.sent_friend_request_uids || []);
  const friendSet = new Set(safeInbox.friend_uids || []);
  const myLocation = useAuthStore((s) => s?.profile?.location);
  const showLocationHint = !!deckRadius && !(myLocation && myLocation.trim());

  // Initial + refetch on prop change. Wrapped so an unhandled promise
  // rejection can never freeze the page.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await fetchDeck();
      } catch (err) {
        // The store already stores `error` internally, but a throw
        // that bypasses that would land here. Log + surface a toast.
        if (!cancelled) {
    
          console.error("Discovery.fetchDeck threw:", err);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [fetchDeck]);

  // If the last fetch failed with a transient error (network hiccup),
  // auto-retry once after 3s. After that it becomes a manual retry.
  useEffect(() => {
    if (!error) return undefined;
    if (autoRetryCount >= 1) return undefined;
    const t = setTimeout(() => {
      setAutoRetryCount((n) => n + 1);
      fetchDeck().catch(() => { /* the store has stored the error */ });
    }, 3000);
    return () => clearTimeout(t);
  }, [error, autoRetryCount, fetchDeck]);

  const flashToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast((curr) => (curr === msg ? null : curr)), 2200);
  };

  const handleNice = async (e, player) => {
    try {
      e.stopPropagation();
      e.preventDefault();
      if (!player?.uid) return;
      await likePlayer(player);
      flashToast(`Nice — you tagged ${player.name || 'them'} 💚`);
    } catch (err) {

      console.error("handleNice failed:", err);
      flashToast("Couldn't like — try again");
    }
  };

  const handlePlayer = async (e, player) => {
    try {
      e.stopPropagation();
      e.preventDefault();
      if (!player?.uid) return;
      const res = await sendFriendRequest(player);
      if (res?.error) flashToast(`Request failed: ${res.error}`);
      else if (res?.friended) flashToast(`✅ You're now players with ${player.name || 'them'} 🥏`);
      else flashToast(`✅ Player request sent to ${player.name || 'them'}`);
    } catch (err) {

      console.error("handlePlayer failed:", err);
      flashToast("Couldn't send request — try again");
    }
  };

  const handleMessage = (e, player) => {
    try {
      e.stopPropagation();
      e.preventDefault();
      if (!player?.uid) return;
      setComposeRecipient({
        uid: player.uid,
        name: player.name,
        profilePictureUrl: player.profilePictureUrl,
      });
    } catch (err) {

      console.error("handleMessage failed:", err);
    }
  };

  const openProfile = (uid) => {
    if (!uid) return;
    try { navigate(`/players/${uid}`); } catch (err) {

      console.error("openProfile failed:", err);
    }
  };

  const handleRetryFetch = () => {
    setAutoRetryCount(0);
    fetchDeck().catch(() => { /* store owns error state */ });
  };

  const radiusBar = (
    <div
      className="flex flex-wrap items-center justify-center gap-2 mb-3"
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

  const interestBar = (
    <div
      className="flex flex-wrap items-center justify-center gap-2 mb-5"
      data-testid="discovery-interest-bar"
    >
      <span className="text-sm font-semibold text-gray-700 mr-1">🥏 Interested in:</span>
      {INTEREST_OPTIONS.map((opt) => {
        const active = (deckInterestedIn ?? null) === opt.value;
        return (
          <button
            key={opt.label}
            type="button"
            onClick={() => setDeckInterestedIn(opt.value)}
            className={
              active
                ? 'bg-disc-gold text-white font-bold text-sm px-3 py-1.5 rounded-full shadow'
                : 'border border-disc-gold text-disc-gold hover:bg-disc-gold/10 font-semibold text-sm px-3 py-1.5 rounded-full'
            }
            data-testid={`interest-option-${opt.value ?? 'any'}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );

  if (loading && safeDeck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-loading">
        {radiusBar}
        {interestBar}
        <div className="mt-6">
          <PlayerGridSkeleton count={8} />
        </div>
      </div>
    );
  }

  // Fetch failed AND we have nothing to show — surface a friendly retry
  // instead of the misleading "No more players" empty state.
  if (error && safeDeck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-error">
        {radiusBar}
        {interestBar}
        <div className="max-w-md mx-auto bg-white border border-red-200 rounded-2xl shadow-sm p-8 text-center">
          <div className="text-3xl mb-3" aria-hidden="true">🥏</div>
          <h2 className="text-xl font-bold text-gray-800 mb-2">
            We couldn&apos;t load the roster
          </h2>
          <p className="text-sm text-gray-600 mb-5">
            {autoRetryCount >= 1
              ? "Auto-retry didn't clear it — please try again."
              : "Auto-retrying in a moment… or tap below to retry now."}
          </p>
          <button
            type="button"
            onClick={handleRetryFetch}
            data-testid="discovery-error-retry-btn"
            className="px-5 py-2.5 rounded-full bg-disc-green hover:bg-disc-green/90 text-white font-semibold text-sm"
          >
            Try again
          </button>
          <details className="mt-5 text-left">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 font-mono">
              Error details
            </summary>
            <pre className="mt-2 text-[10px] text-gray-500 bg-gray-50 rounded p-2 overflow-x-auto whitespace-pre-wrap">
              {String(error)}
            </pre>
          </details>
        </div>
      </div>
    );
  }

  if (safeDeck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-empty">
        {radiusBar}
        {interestBar}
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-4">
            {deckRadius || deckInterestedIn
              ? 'No players match those filters 📍'
              : 'No more players to discover! 🎉'}
          </h2>
          <p className="text-gray-600">
            {deckRadius || deckInterestedIn ? (
              <>
                Try widening your filters or{' '}
                <button
                  type="button"
                  className="text-disc-green font-bold underline"
                  onClick={() => {
                    setDeckRadius(null);
                    setDeckInterestedIn(null);
                  }}
                  data-testid="discovery-reset-radius"
                >
                  reset to Anywhere · Any
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
      <DismissibleBanner
        storageKey="ace_invite_friends_dismissed"
        title="Loving the app? Bring your friends!"
        body="Share the link with your favorite people and suggest us to your circle today."
        testId="discovery-invite-banner"
      />
      <header className="mb-4 text-center">
        <h1 className="text-4xl font-bold text-disc-green mb-1">Find Your Ace Match</h1>
        <p className="text-gray-600 text-sm" data-testid="discovery-count">
          {(() => {
            // The visible count reflects players you can still act on —
            // friends and already-requested users are shown in the deck
            // (with a status pill) but shouldn't inflate the counter.
            const actionable = safeDeck.filter(
              (p) => p && p.uid && !friendSet.has(p.uid) && !sentSet.has(p.uid)
            ).length;
            return (
              <>
                {actionable} player{actionable === 1 ? '' : 's'} to discover —
                tap a card to view their full profile
              </>
            );
          })()}
        </p>
      </header>

      {radiusBar}
      {interestBar}

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
        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"
        data-testid="discovery-grid"
      >
        {safeDeck.map((player) => {
          // Skip malformed player rows so a single bad row can't crash the grid.
          if (!player || !player.uid) return null;
          const isFriend = friendSet.has(player.uid);
          const sent = sentSet.has(player.uid);
          const actions = (
            <div
              className="flex flex-wrap gap-x-5 gap-y-1 items-center"
              onClick={(e) => e.stopPropagation()}
              data-testid={`discovery-actions-${player.uid}`}
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
          );

          return (
            <div
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
              className="cursor-pointer hover:ring-2 hover:ring-disc-green/60 rounded-2xl transition"
              data-testid={`discovery-card-${player.uid}`}
              aria-label={`Open ${player.name || 'player'}'s full profile`}
            >
              <PublicProfilePreview player={player} actions={actions} />
            </div>
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

      {composeRecipient && (
        <MessageComposeModal
          recipient={composeRecipient}
          onClose={() => setComposeRecipient(null)}
          onSent={(r) => flashToast(`✅ Message sent to ${r.name || 'them'}`)}
        />
      )}
    </div>
  );
}
