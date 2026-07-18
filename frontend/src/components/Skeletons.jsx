/**
 * Lightweight skeleton placeholders for feed / discovery / league lists.
 * The pulsing shimmer is a Tailwind `animate-pulse` — no keyframe CSS
 * required. Each skeleton mimics the SHAPE of its real content so the
 * layout doesn't jump when data arrives (Cumulative Layout Shift = 0).
 */

export function FeedPostSkeleton() {
  return (
    <article
      className="bg-white rounded-2xl shadow-lg p-5 animate-pulse"
      data-testid="feed-post-skeleton"
    >
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full bg-gray-200" />
        <div className="flex-1 space-y-2">
          <div className="h-3 w-32 bg-gray-200 rounded" />
          <div className="h-2 w-20 bg-gray-100 rounded" />
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <div className="h-3 w-full bg-gray-200 rounded" />
        <div className="h-3 w-11/12 bg-gray-200 rounded" />
        <div className="h-3 w-3/4 bg-gray-200 rounded" />
      </div>
      <div className="mt-4 h-48 bg-gray-100 rounded-xl" />
    </article>
  );
}

export function FeedSkeleton({ count = 3 }) {
  return (
    <div className="space-y-5" data-testid="feed-skeleton">
      {Array.from({ length: count }, (_, i) => (
        <FeedPostSkeleton key={i} />
      ))}
    </div>
  );
}

export function PlayerCardSkeleton() {
  return (
    <div
      className="bg-white rounded-xl shadow p-4 animate-pulse"
      data-testid="player-card-skeleton"
    >
      <div className="h-40 bg-gray-200 rounded-lg mb-3" />
      <div className="h-4 w-3/4 bg-gray-200 rounded mb-2" />
      <div className="h-3 w-1/2 bg-gray-100 rounded" />
    </div>
  );
}

export function PlayerGridSkeleton({ count = 6 }) {
  return (
    <div
      className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4"
      data-testid="player-grid-skeleton"
    >
      {Array.from({ length: count }, (_, i) => (
        <PlayerCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function LeagueCardSkeleton() {
  return (
    <div
      className="rounded-2xl border border-gray-200 p-5 animate-pulse"
      data-testid="league-card-skeleton"
    >
      <div className="h-3 w-20 bg-gray-200 rounded mb-3" />
      <div className="h-5 w-3/4 bg-gray-200 rounded mb-2" />
      <div className="h-3 w-1/2 bg-gray-100 rounded" />
      <div className="mt-4 flex gap-2">
        <div className="h-6 w-16 bg-gray-100 rounded-full" />
        <div className="h-6 w-16 bg-gray-100 rounded-full" />
      </div>
    </div>
  );
}

export function LeagueGridSkeleton({ count = 4 }) {
  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 gap-4"
      data-testid="league-grid-skeleton"
    >
      {Array.from({ length: count }, (_, i) => (
        <LeagueCardSkeleton key={i} />
      ))}
    </div>
  );
}
