import { useState } from 'react';

/**
 * Alpha-stage welcome banner shown on the Feed (home) page.
 * - Persists its "dismissed" state per-browser in localStorage so users
 *   only see it once. Bumping `STORAGE_KEY` re-shows it for everyone.
 * - The "let me know" link is a mailto by default; swap it for a feedback
 *   form / bug tracker URL if you prefer.
 */
const STORAGE_KEY = 'ace-alpha-banner-dismissed-v1';
const CONTACT_HREF = 'mailto:juststraycreations@gmail.com?subject=Ace%20Chasers%20feedback';

export default function AlphaBanner() {
  const [dismissed, setDismissed] = useState(() => {
    // Read once at mount; SSR-safe guard kept for completeness even though
    // Vite is client-only here.
    if (typeof window === 'undefined') return true;
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  });

  const handleDismiss = () => {
    window.localStorage.setItem(STORAGE_KEY, '1');
    setDismissed(true);
  };

  if (dismissed) return null;

  return (
    <div
      className="relative rounded-2xl border border-disc-gold/40 bg-gradient-to-r from-yellow-50 to-amber-50 px-5 py-4 mb-6 shadow-sm"
      data-testid="alpha-banner"
      role="status"
    >
      <button
        type="button"
        onClick={handleDismiss}
        className="absolute top-3 right-3 text-amber-700/70 hover:text-amber-900 font-bold leading-none text-lg w-6 h-6 flex items-center justify-center rounded hover:bg-amber-200/60 transition"
        aria-label="Dismiss welcome banner"
        data-testid="alpha-banner-dismiss"
      >
        ✕
      </button>
      <div className="pr-8 text-amber-900">
        <p className="font-bold text-base flex items-center gap-2">
          <span aria-hidden="true">🚧</span> Welcome — Ace Chasers is in alpha
        </p>
        <p className="mt-1 text-sm leading-relaxed">
          This site is currently in its alpha development stage. Because it&apos;s a work in
          progress, you might encounter a few bugs or rough edges along the way. If you spot
          anything acting up,{' '}
          <a
            href={CONTACT_HREF}
            className="font-semibold underline underline-offset-2 text-disc-green hover:text-disc-green/80"
            data-testid="alpha-banner-contact"
          >
            let me know
          </a>{' '}
          so I can fix it! Check back often — I&apos;m actively updating and adding new features.
        </p>
      </div>
    </div>
  );
}
