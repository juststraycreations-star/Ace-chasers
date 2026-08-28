import { useEffect } from 'react';

const STORAGE_KEY = 'ace_cache_notice_dismissed_v1';

/**
 * Modal version of the cache hint. Only appears on Login when a sign-in
 * attempt fails with a network-style error, so it surfaces exactly when
 * it's useful instead of cluttering the form for everyone.
 *
 * - Auto-skipped if the user has dismissed it before (localStorage flag).
 * - Closes on ✕, backdrop click, or "Got it".
 */
export default function CacheNoticeModal({ open, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* ignore — private mode etc. */
    }
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-[80] bg-black/60 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cache-modal-title"
      onClick={onClose}
      data-testid="cache-notice-modal"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3 right-3 text-gray-400 hover:text-gray-700 text-xl leading-none"
          data-testid="cache-notice-modal-close"
        >
          ✕
        </button>
        <div className="flex items-start gap-3">
          <span aria-hidden="true" className="text-2xl">⚠️</span>
          <div className="flex-1">
            <h3
              id="cache-modal-title"
              className="font-bold text-disc-green text-lg mb-1"
            >
              Sign-in trouble?
            </h3>
            <p className="text-sm text-gray-700 leading-snug">
              If you keep seeing a “network error,” your browser may be caching
              an older version of the site. Try a private / incognito window, or
              clear site data for this page and reload.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="mt-5 w-full bg-disc-green hover:bg-disc-green/90 text-white font-semibold py-2.5 rounded-lg transition"
          data-testid="cache-notice-modal-ok"
        >
          Got it — don&apos;t show again
        </button>
      </div>
    </div>
  );
}
