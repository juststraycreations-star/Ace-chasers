import { useEffect, useRef, useState } from 'react';

/**
 * CommentActionsMenu — triple-dot popover next to a comment.
 *
 * Two trigger paths, per product spec:
 *   1. Explicit tap of the ⋯ button (both mobile and desktop).
 *   2. Long-press (~450 ms) anywhere on the parent comment row, which
 *      dispatches a `commentActions:longPress` CustomEvent that this
 *      component listens for. That keeps this component self-contained
 *      — the row doesn't need a ref into it.
 *
 * Only renders the "Delete comment" action for now, but the surface
 * is deliberately extensible (Report, Copy, etc. drop into the same
 * <ul>).
 */
export default function CommentActionsMenu({ comment, onDelete }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  // Click-outside close.
  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Long-press channel — subscribe to the app-wide CustomEvent so the
  // parent row can trigger us without a ref.
  useEffect(() => {
    const onLongPress = (e) => {
      if (e.detail?.commentId === comment.id) setOpen(true);
    };
    window.addEventListener('commentActions:longPress', onLongPress);
    return () => window.removeEventListener('commentActions:longPress', onLongPress);
  }, [comment.id]);

  return (
    <div ref={rootRef} className="relative" data-testid={`comment-actions-${comment.id}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-gray-400 hover:text-gray-700 px-2 py-1 rounded-full transition
                   focus:outline-none focus:ring-2 focus:ring-disc-green/30
                   text-lg leading-none flex-shrink-0"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Comment actions"
        title="Comment actions"
        data-testid={`comment-actions-btn-${comment.id}`}
      >
        {/* Unicode triple-dot glyph so we don't ship an icon dep for one button */}
        ⋯
      </button>
      {open && (
        <ul
          role="menu"
          className="absolute right-0 top-full mt-1 z-30 min-w-[10rem]
                     bg-white text-gray-800 rounded-xl shadow-2xl
                     border border-gray-100 overflow-hidden py-1"
          data-testid={`comment-actions-menu-${comment.id}`}
        >
          <li>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onDelete();
              }}
              className="w-full text-left px-4 py-2 text-sm text-red-600
                         hover:bg-red-50 font-semibold"
              data-testid={`comment-delete-${comment.id}`}
            >
              Delete comment
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
