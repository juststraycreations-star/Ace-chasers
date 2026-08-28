/**
 * FirstRunBadge — a small, premium disc-golf micro-badge shown next to
 * founding-member display names. Renders inline; tooltip on hover.
 *
 * Deliberately restrained: 16-20px inline SVG of concentric flight rings
 * on a slate-900 chip with a bronze/amber-30 border. No stars, no cartoons.
 */
export default function FirstRunBadge({ size = 16, className = "" }) {
  const s = typeof size === "number" ? `${size}px` : size;
  return (
    <span
      className={`relative group inline-flex items-center justify-center align-middle rounded-full bg-slate-900 border border-amber-500/30 shadow-[inset_0_0_0_1px_rgba(180,120,40,0.15)] transition-colors hover:border-amber-500/60 ${className}`}
      style={{ width: s, height: s, padding: 0 }}
      data-testid="first-run-badge"
      aria-label="First Run founding member"
    >
      <svg
        viewBox="0 0 20 20"
        width="70%"
        height="70%"
        fill="none"
        stroke="currentColor"
        className="text-amber-400/90"
        aria-hidden="true"
      >
        <circle cx="10" cy="10" r="8.25" strokeWidth="1" />
        <circle cx="10" cy="10" r="5.6" strokeWidth="0.6" opacity="0.75" />
        <circle cx="10" cy="10" r="2.6" strokeWidth="0.5" opacity="0.55" />
        <circle cx="10" cy="10" r="0.9" fill="currentColor" stroke="none" opacity="0.7" />
      </svg>
      {/* Hover tooltip */}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1 text-[10px] font-medium tracking-wide text-amber-100 opacity-0 shadow-lg ring-1 ring-amber-500/20 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 z-50"
        data-testid="first-run-badge-tooltip"
      >
        First Run: One of the first 100 players to card up.
      </span>
    </span>
  );
}
