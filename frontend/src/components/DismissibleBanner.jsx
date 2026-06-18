import { useEffect, useState } from 'react';

/**
 * Dismissible top-of-page banner.
 * Once a user clicks ✕, the dismissal is remembered in localStorage under
 * the given storage key so they don't see it again.
 */
export default function DismissibleBanner({
  storageKey,
  title,
  body,
  testId,
}) {
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    try {
      setHidden(localStorage.getItem(storageKey) === '1');
    } catch (_e) {
      setHidden(false);
    }
  }, [storageKey]);

  if (hidden) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(storageKey, '1');
    } catch (_e) {
      /* no-op */
    }
    setHidden(true);
  };

  return (
    <div
      className="mb-6 flex items-start gap-3 bg-disc-green/10 border-2 border-disc-green/40 rounded-xl px-4 py-3 text-sm text-gray-800 shadow-sm"
      role="status"
      data-testid={testId}
    >
      <span className="text-lg leading-none mt-0.5" aria-hidden="true">🥏</span>
      <div className="flex-1">
        <p className="font-bold text-disc-green">{title}</p>
        <p className="text-gray-700 mt-0.5">{body}</p>
      </div>
      <button
        type="button"
        onClick={dismiss}
        className="text-gray-500 hover:text-gray-800 font-bold leading-none px-1"
        aria-label="Dismiss"
        data-testid={`${testId}-dismiss`}
      >
        ✕
      </button>
    </div>
  );
}
