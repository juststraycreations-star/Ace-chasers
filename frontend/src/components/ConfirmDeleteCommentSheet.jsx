import { useEffect } from 'react';

/**
 * ConfirmDeleteCommentSheet — destructive-action confirmation.
 *
 * UX pattern per spec: **mobile-first bottom sheet** that snaps to a
 * centered modal on ≥ sm. Same component drives both surfaces so the
 * copy + action buttons stay consistent.
 *
 *   • Cancel     — neutral button, dismisses the sheet.
 *   • Delete     — destructive red text button, calls `onConfirm`.
 *   • Backdrop   — dismisses (mobile-native gesture parity).
 *   • Escape key — dismisses (desktop accessibility).
 *   • Safe area  — `env(safe-area-inset-bottom)` respected on iPhone
 *                  home indicators.
 */
export default function ConfirmDeleteCommentSheet({ open, onCancel, onConfirm }) {
  // Escape-to-dismiss for keyboard users.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex flex-col justify-end items-stretch
                 sm:justify-center sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-comment-sheet-title"
      data-testid="delete-comment-sheet"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Dismiss confirmation"
        onClick={onCancel}
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-[1px]"
        data-testid="delete-comment-sheet-backdrop"
      />
      {/* Sheet / modal body */}
      <div
        className="relative w-full sm:max-w-sm bg-white text-slate-900
                   rounded-t-2xl sm:rounded-2xl shadow-2xl border border-gray-100
                   p-5 pb-[max(env(safe-area-inset-bottom),1.25rem)]
                   sm:pb-5 animate-in slide-in-from-bottom sm:slide-in-from-bottom-0"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Grabber — visual affordance that this is a mobile sheet */}
        <div
          className="mx-auto mb-3 h-1 w-10 rounded-full bg-gray-300 sm:hidden"
          aria-hidden="true"
        />
        <h2
          id="delete-comment-sheet-title"
          className="text-base font-bold text-slate-900 mb-2"
        >
          Delete this comment?
        </h2>
        <p className="text-sm text-slate-600 mb-5">
          Delete this comment? You&apos;ll have 5 seconds to undo before it&apos;s
          permanently removed.
        </p>
        <div className="flex items-center gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="text-sm font-medium text-slate-600 hover:text-slate-900
                       px-4 py-2 rounded-full transition"
            data-testid="delete-comment-cancel-btn"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="text-sm font-bold text-red-600 hover:text-white
                       hover:bg-red-600 border border-red-200 hover:border-red-600
                       px-4 py-2 rounded-full transition"
            data-testid="delete-comment-confirm-btn"
            autoFocus
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
