import { useEffect, useState } from 'react';

const STORAGE_KEY = 'ace_get_the_app_dismissed_v1';

/**
 * Play Store download URL. Set this to the real Play listing URL once the
 * app is published — the banner will start linking to it automatically.
 * Empty string ⇒ banner shows a "coming soon" pill instead of a link.
 *
 * Example after submission:
 *   const PLAY_STORE_URL = 'https://play.google.com/store/apps/details?id=net.acechasers.twa';
 */
const PLAY_STORE_URL = '';

/**
 * A Google-Play-style CTA that shows on the Feed after sign-in so existing
 * users know an installable Android app is available. Dismissible.
 * Auto-hides on non-mobile-friendly widths only if the user has already
 * dismissed it (still visible on desktop by default so power users can
 * hand out the link to friends).
 */
export default function GetTheAppBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY)) return;
    } catch {
      /* private mode etc. */
    }
    setVisible(true);
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* ignore */
    }
    setVisible(false);
  };

  const hasLink = Boolean(PLAY_STORE_URL);

  const inner = (
    <>
      <div
        className="w-10 h-10 rounded-lg bg-white/15 flex items-center justify-center flex-shrink-0"
        aria-hidden="true"
      >
        {/* Play triangle — universal "app" mark */}
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold leading-tight">
          {hasLink ? 'Get Ace Chasers on Google Play' : 'Ace Chasers is coming to Google Play'}
        </p>
        <p className="text-xs text-white/80 mt-0.5">
          {hasLink
            ? 'Install the Android app for a smoother experience.'
            : 'The Android app launches soon — this browser experience will also install as a home-screen app on your phone.'}
        </p>
      </div>
      {hasLink && (
        <span className="hidden sm:inline-flex bg-white text-disc-green text-xs font-bold px-3 py-1.5 rounded-lg flex-shrink-0">
          Install
        </span>
      )}
    </>
  );

  return (
    <div
      className="mb-4 rounded-xl bg-gradient-to-r from-disc-green to-emerald-800 text-white shadow-md relative"
      data-testid="get-the-app-banner"
    >
      {hasLink ? (
        <a
          href={PLAY_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-3 pr-10 hover:brightness-110 transition"
          data-testid="get-the-app-link"
        >
          {inner}
        </a>
      ) : (
        <div className="flex items-center gap-3 px-4 py-3 pr-10">{inner}</div>
      )}
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        className="absolute top-1.5 right-2 text-white/70 hover:text-white text-lg leading-none w-6 h-6 flex items-center justify-center"
        data-testid="get-the-app-dismiss"
      >
        ✕
      </button>
    </div>
  );
}
