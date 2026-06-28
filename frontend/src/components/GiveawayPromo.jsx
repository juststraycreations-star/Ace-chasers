import DiscIcon from './DiscIcon';

/**
 * Launch giveaway promo card shown on the Login / Sign Up pages.
 * Drawing date: Sunday, July 19, 2026.
 */
export default function GiveawayPromo() {
  return (
    <div
      className="mb-6 rounded-2xl border-2 border-disc-gold bg-gradient-to-br from-amber-50 via-white to-amber-50 p-5 shadow-md"
      data-testid="giveaway-promo"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-2xl" aria-hidden="true">🏆</span>
        <h2 className="font-bold text-disc-green text-lg leading-tight">
          LAUNCH GIVEAWAY
        </h2>
      </div>

      <p className="text-sm text-gray-800 font-semibold leading-snug mb-3">
        Win a <span className="text-disc-green">GTO Leopard3</span>,
        <span className="text-disc-green"> Proto Glow</span>, &amp;
        <span className="text-disc-green"> Pro Series Duo Pack!</span>
      </p>

      <p className="text-xs text-gray-700 leading-snug mb-3">
        To celebrate our launch, we&apos;re gifting a premium 3-disc player
        pack to one lucky community member.
      </p>

      <div className="text-xs text-gray-800 space-y-1.5 mb-3">
        <p className="font-semibold text-gray-900">How to enter:</p>
        <p className="flex gap-2">
          <span aria-hidden="true">1️⃣</span>
          <span>Create a free profile right now.</span>
        </p>
        <p className="flex gap-2">
          <span aria-hidden="true">2️⃣</span>
          <span>
            Post a quick update, photo, or bag check on our live feed.
          </span>
        </p>
      </div>

      <div className="rounded-lg bg-disc-green/10 border border-disc-green/30 px-3 py-2 flex items-center gap-2">
        <DiscIcon className="h-4 w-4 text-disc-green flex-shrink-0" />
        <p className="text-xs text-disc-green font-semibold leading-snug">
          Winner drawn from the feed on Sunday, July 19, 2026. Good luck &amp;
          happy hunting!
        </p>
      </div>
    </div>
  );
}
