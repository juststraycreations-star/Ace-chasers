import { useEffect, useState } from 'react';

const STORAGE_KEY = 'ace_cache_notice_dismissed_v1';

/**
 * Small dismissible notice shown on the Login + SignUp pages.
 * Tells users to try incognito / clear site data if Google sign-in
 * fails with a "network error" — the most common failure mode while
 * we're still iterating on production builds.
 */
export default function CacheNotice() {
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    const dismissed = localStorage.getItem(STORAGE_KEY);
    if (!dismissed) setHidden(false);
  }, []);

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setHidden(true);
  };

  if (hidden) return null;

  return (
    <div
      className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 flex items-start gap-2"
      data-testid="cache-notice"
    >
      <span aria-hidden="true" className="text-sm leading-none">⚠️</span>
      <div className="flex-1 leading-snug">
        <strong className="font-semibold">Sign-in trouble?</strong> If you see a
        “network error,” your browser may be caching an older version of the
        site. Try a private/incognito window, or clear site data for this page
        and reload.
      </div>
      <button
        type="button"
        onClick={dismiss}
        className="text-amber-700 hover:text-amber-900 text-xs font-bold"
        data-testid="cache-notice-dismiss"
        aria-label="Dismiss notice"
      >
        ✕
      </button>
    </div>
  );
}
