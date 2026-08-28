import { useEffect, useRef, useState } from 'react';

/**
 * SwipeToRevealDelete — iOS-Mail-style swipe-left reveals a red
 * "Delete" button behind the child content. Tap the button to fire
 * `onDelete`. The wrapper snaps back on outside-tap / touch-cancel.
 *
 * Deliberately minimal:
 *  • Touch only — mouse users have the ⋯ menu / right-click for the
 *    same policy.
 *  • Threshold: snap open at 60 px, snap closed under it. The button
 *    is 96 px wide so at rest it's fully tucked behind the row.
 *  • No horizontal-vs-vertical arbitration for now — we bail out if
 *    the initial delta looks vertical (avoids fighting page scroll).
 */
const REVEAL_PX = 96;
const OPEN_THRESHOLD = 60;
const VERTICAL_CANCEL = 12; // if a touch moves this many vertical px before crossing horizontal, treat as scroll.

export default function SwipeToRevealDelete({ enabled, onDelete, children }) {
  const [translate, setTranslate] = useState(0);
  const [transitioning, setTransitioning] = useState(false);
  const startRef = useRef(null);
  const rowRef = useRef(null);

  // Snap closed when any other row opens — no more than one row is
  // open at a time on the page.
  useEffect(() => {
    if (!enabled) return undefined;
    const onOpen = (e) => {
      if (e.detail?.owner !== rowRef.current) setTranslate(0);
    };
    window.addEventListener('swipeReveal:open', onOpen);
    return () => window.removeEventListener('swipeReveal:open', onOpen);
  }, [enabled]);

  if (!enabled) return <>{children}</>;

  const openIt = () => {
    setTransitioning(true);
    setTranslate(-REVEAL_PX);
    window.dispatchEvent(
      new CustomEvent('swipeReveal:open', { detail: { owner: rowRef.current } })
    );
  };
  const closeIt = () => {
    setTransitioning(true);
    setTranslate(0);
  };

  const onTouchStart = (e) => {
    const t = e.touches[0];
    startRef.current = { x: t.clientX, y: t.clientY, base: translate };
    setTransitioning(false);
  };
  const onTouchMove = (e) => {
    const s = startRef.current;
    if (!s) return;
    const t = e.touches[0];
    const dx = t.clientX - s.x;
    const dy = t.clientY - s.y;
    // Bail out if the gesture looks like a vertical scroll before we've
    // moved much horizontally — protects native page scrolling.
    if (Math.abs(dy) > VERTICAL_CANCEL && Math.abs(dy) > Math.abs(dx)) {
      startRef.current = null;
      setTransitioning(true);
      setTranslate(s.base);
      return;
    }
    // Only allow leftward drag (dx < 0). Rightward drag from open state
    // reduces the reveal, capped at 0.
    const next = Math.min(0, Math.max(-REVEAL_PX * 1.2, s.base + dx));
    setTranslate(next);
  };
  const onTouchEnd = () => {
    startRef.current = null;
    if (Math.abs(translate) >= OPEN_THRESHOLD) openIt();
    else closeIt();
  };

  const onDeleteClick = () => {
    // Close first so the row visually disappears with the animation
    // rather than jumping back to 0 mid-fade.
    setTranslate(0);
    onDelete();
  };

  return (
    <div
      ref={rowRef}
      className="relative overflow-hidden rounded-2xl"
      data-testid="swipe-reveal-row"
    >
      {/* Revealed action pane — pinned behind the sliding content. */}
      <button
        type="button"
        onClick={onDeleteClick}
        aria-label="Delete comment"
        data-testid="swipe-reveal-delete-btn"
        className="absolute inset-y-0 right-0 flex items-center justify-center
                   bg-red-600 text-white font-bold text-sm px-4
                   focus:outline-none focus:ring-2 focus:ring-red-300
                   active:bg-red-700"
        style={{ width: REVEAL_PX }}
      >
        Delete
      </button>
      {/* Sliding row */}
      <div
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={() => {
          startRef.current = null;
          closeIt();
        }}
        onClick={() => {
          // Tap the row while open → close it (matches iOS Mail).
          if (translate !== 0) closeIt();
        }}
        className={
          'relative bg-transparent ' +
          (transitioning ? 'transition-transform duration-150 ease-out' : '')
        }
        style={{ transform: `translateX(${translate}px)` }}
      >
        {children}
      </div>
    </div>
  );
}
