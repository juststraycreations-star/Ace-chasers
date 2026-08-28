import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../lib/api';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import { enqueueCommentDelete } from '../lib/offlineQueue';
import CommentActionsMenu from './CommentActionsMenu';
import ConfirmDeleteCommentSheet from './ConfirmDeleteCommentSheet';
import SwipeToRevealDelete from './SwipeToRevealDelete';

/**
 * Per-post Nice button + collapsible comment thread.
 *
 * Optimistic UI: clicking Nice updates the count immediately and rolls back
 * if the server rejects. Comments expand on first click and lazy-load.
 */
export default function PostInteractions({ post }) {
  const isReview = post.kind === 'disc_review';
  const [react, setReact] = useState({
    liked: !!post.liked_by_me,
    disliked: !!post.disliked_by_me,
    up: post.nice_count || 0,
    down: post.down_count || 0,
  });
  const [showComments, setShowComments] = useState(false);
  const [comments, setComments] = useState(null);
  const [commentText, setCommentText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [count, setCount] = useState(post.comment_count || 0);
  // Server-supplied preview of up to 3 latest comments — drives the inline
  // teaser that's visible without expanding the full thread.
  const [preview, setPreview] = useState(post.recent_comments || []);
  // Which comment (if any) is queued for the delete confirmation sheet.
  const [pendingDelete, setPendingDelete] = useState(null);

  // Best-effort backfill of `can_delete` for legacy cached responses.
  // Server-of-truth is set inside posts_router.py; this only matters
  // during the first render after an app update that ships new logic
  // against a service-worker-cached feed payload.
  const viewerOwnsPost = !!post.is_mine;
  const canDelete = (c) => c.can_delete || c.is_mine || viewerOwnsPost;

  const sendReaction = async (value) => {
    const prev = react;
    // Optimistic: compute the next state locally.
    const next = { ...prev };
    if (value === 'up') {
      if (prev.liked) { next.liked = false; next.up = Math.max(0, prev.up - 1); }
      else {
        next.liked = true; next.up = prev.up + 1;
        if (prev.disliked) { next.disliked = false; next.down = Math.max(0, prev.down - 1); }
      }
    } else { // down
      if (prev.disliked) { next.disliked = false; next.down = Math.max(0, prev.down - 1); }
      else {
        next.disliked = true; next.down = prev.down + 1;
        if (prev.liked) { next.liked = false; next.up = Math.max(0, prev.up - 1); }
      }
    }
    setReact(next);
    try {
      const url = isReview
        ? `/posts/${post.id}/react?value=${value}`
        : `/posts/${post.id}/nice`;
      const res = await api.post(url);
      setReact({
        liked: !!res.data.liked_by_me,
        disliked: !!res.data.disliked_by_me,
        up: res.data.nice_count,
        down: res.data.down_count ?? 0,
      });
    } catch (err) {
      console.error('reaction failed', err);
      setReact(prev);
    }
  };

  const toggleUp = () => sendReaction('up');
  const toggleDown = () => sendReaction('down');

  const openComments = async () => {
    setShowComments((v) => !v);
    if (comments === null) {
      try {
        const res = await api.get(`/posts/${post.id}/comments`);
        setComments(res.data);
        setCount(res.data.length);
      } catch (err) {
        console.error('list comments failed', err);
        setComments([]);
      }
    }
  };

  const submitComment = async (e) => {
    e.preventDefault();
    const body = commentText.trim();
    if (!body || submitting) return;
    setSubmitting(true);
    try {
      const res = await api.post(`/posts/${post.id}/comments`, { body });
      setComments((prev) => [...(prev || []), res.data]);
      setCommentText('');
      setCount((c) => c + 1);
      // Keep the preview in sync (keep last 3 chronological).
      setPreview((prev) => [...prev, res.data].slice(-3));
    } catch (err) {
      console.error('add comment failed', err);
      alert(err?.response?.data?.detail || 'Could not post comment');
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Deferred-delete + Undo pattern (iOS Mail / Gmail style):
   *   1. Snapshot the comment before removing it so we can restore.
   *   2. Optimistically remove from preview + full-thread lists.
   *   3. Show a 5-second toast with an "Undo" action.
   *   4. Schedule the actual DELETE for `+5000 ms`.
   *   5. If Undo tapped: clear the timer AND put the comment back.
   *      If offline: `enqueueCommentDelete` still fires at t+5s so
   *      the intent survives even without connectivity.
   *      On unmount: fire the pending delete synchronously so we
   *      don't lose the user's intent when they navigate away.
   */
  const pendingDeletesRef = useRef(new Map()); // commentId → { timer, restore, commit }
  const UNDO_MS = 5000;

  const doDeleteNow = (postId, commentId) => {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      enqueueCommentDelete({ postId, commentId });
      return;
    }
    api
      .delete(`/posts/${postId}/comments/${commentId}`)
      .catch((err) => {
        const status = err?.response?.status;
        if (!status || status >= 500) {
          enqueueCommentDelete({ postId, commentId });
        }
        // 4xx (already-gone / 403) → nothing to do, comment is out
        // of the local UI and either doesn't exist on the server or
        // shouldn't be touched by this viewer.
      });
  };

  const removeComment = (comment) => {
    // Snapshot BEFORE mutation so rollback is trivial.
    const previewSnapshot = preview;
    const commentsSnapshot = comments;
    const countSnapshot = count;

    setPreview((prev) => prev.filter((c) => c.id !== comment.id));
    setComments((prev) =>
      prev === null ? prev : prev.filter((c) => c.id !== comment.id)
    );
    setCount((c) => Math.max(0, c - 1));

    const restore = () => {
      setPreview(previewSnapshot);
      setComments(commentsSnapshot);
      setCount(countSnapshot);
    };
    const commit = () => doDeleteNow(post.id, comment.id);

    // Schedule the delete + register in the ref so unmount can flush.
    const timer = setTimeout(() => {
      commit();
      pendingDeletesRef.current.delete(comment.id);
    }, UNDO_MS);
    pendingDeletesRef.current.set(comment.id, { timer, restore, commit });

    // Sonner supports an inline action button — the whole undo UX is
    // one line here.
    toast('Comment deleted', {
      description: comment.body.slice(0, 60) + (comment.body.length > 60 ? '…' : ''),
      duration: UNDO_MS,
      action: {
        label: 'Undo',
        onClick: () => {
          const entry = pendingDeletesRef.current.get(comment.id);
          if (!entry) return;
          clearTimeout(entry.timer);
          pendingDeletesRef.current.delete(comment.id);
          entry.restore();
        },
      },
    });
  };

  // Unmount / route-change safety: flush any pending deletes so the
  // user's intent isn't lost when they navigate away before the 5-second
  // grace expires. Runs commits synchronously; the network POST still
  // fires-and-forgets in the background.
  useEffect(() => {
    const map = pendingDeletesRef.current;
    return () => {
      for (const [, entry] of map.entries()) {
        clearTimeout(entry.timer);
        try {
          entry.commit();
        } catch (_e) {
          /* commit is fire-and-forget already */
        }
      }
      map.clear();
    };
  }, []);

  const confirmPendingDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    await removeComment(target);
  };

  /**
   * Long-press bindings for a comment row. Touch users can hold a
   * comment for ~450 ms to open its actions menu without hunting for
   * the tiny ⋯ button. The actual open is done by dispatching a
   * `commentActions:longPress` CustomEvent that `CommentActionsMenu`
   * subscribes to — keeps ref plumbing out of the list templates.
   */
  const bindLongPress = (comment) => {
    if (!canDelete(comment)) return {}; // no menu for this user → no gesture either
    let timer = null;
    const start = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        window.dispatchEvent(
          new CustomEvent('commentActions:longPress', {
            detail: { commentId: comment.id },
          })
        );
      }, 450);
    };
    const cancel = () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    };
    return {
      onTouchStart: start,
      onTouchEnd: cancel,
      onTouchMove: cancel,
      onTouchCancel: cancel,
      onContextMenu: (e) => {
        // Desktop parity — right-click opens the menu.
        e.preventDefault();
        window.dispatchEvent(
          new CustomEvent('commentActions:longPress', {
            detail: { commentId: comment.id },
          })
        );
      },
    };
  };

  // Swipe-to-reveal is a touch-only affordance. Desktop users still
  // get the ⋯ menu / right-click; enabling swipe there would just be
  // dead code paths, and mouse drag would fight text selection.
  const isTouchDevice =
    typeof window !== 'undefined' &&
    ('ontouchstart' in window || (navigator?.maxTouchPoints ?? 0) > 0);
  const canSwipeDelete = (c) => isTouchDevice && canDelete(c);

  /**
   * Toggle a 👍 Nice reaction on a single comment. Optimistically updates
   * both the preview list and the full-thread list so both surfaces stay
   * in sync. Rolls back on server error.
   */
  const toggleCommentNice = async (commentId) => {
    const apply = (list, mutator) => (list || []).map((c) => (c.id === commentId ? mutator(c) : c));
    const flip = (c) => {
      const wasLiked = !!c.liked_by_me;
      const nextCount = Math.max(0, (c.nice_count || 0) + (wasLiked ? -1 : 1));
      return { ...c, liked_by_me: !wasLiked, nice_count: nextCount };
    };
    setPreview((p) => apply(p, flip));
    setComments((p) => apply(p, flip));
    try {
      const res = await api.post(`/posts/${post.id}/comments/${commentId}/nice`);
      const reconcile = (c) =>
        c.id === commentId
          ? { ...c, liked_by_me: !!res.data.liked_by_me, nice_count: res.data.nice_count }
          : c;
      setPreview((p) => (p || []).map(reconcile));
      setComments((p) => (p === null ? p : p.map(reconcile)));
    } catch (err) {
      console.error('comment nice failed', err);
      // Roll back by flipping again.
      setPreview((p) => apply(p, flip));
      setComments((p) => apply(p, flip));
    }
  };

  /** Append (or set) "Nice! 🥏" inside the comment textarea. */
  const insertNicePhrase = () => {
    setCommentText((curr) => {
      const trimmed = (curr || '').trimEnd();
      const phrase = 'Nice! 🥏';
      const next = trimmed.length ? `${trimmed} ${phrase}` : phrase;
      return next.slice(0, 500);
    });
  };

  /** Small inline Nice button + count, used both in preview rows and the
   *  expanded thread. Keeps the per-comment reaction surface consistent. */
  const renderCommentNice = (c) => (
    <button
      type="button"
      onClick={() => toggleCommentNice(c.id)}
      className={`inline-flex items-center gap-1 text-[11px] font-semibold transition ${
        c.liked_by_me
          ? 'text-disc-green hover:text-disc-green/80'
          : 'text-gray-500 hover:text-disc-green'
      }`}
      data-testid={`comment-nice-btn-${c.id}`}
      aria-pressed={!!c.liked_by_me}
      title="Nice"
    >
      <span aria-hidden="true">👍</span>
      <span>{c.liked_by_me ? 'Nice ✓' : 'Nice'}</span>
      {c.nice_count > 0 && (
        <span
          className="text-[10px] text-gray-500 font-normal"
          data-testid={`comment-nice-count-${c.id}`}
        >
          ({c.nice_count})
        </span>
      )}
    </button>
  );

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      {/* Inline preview of up to 3 most recent comments (server-provided).
          Hidden once the full thread is expanded so we don't render twice. */}
      {preview.length > 0 && !showComments && (
        <ul
          className="space-y-2 mb-3"
          data-testid={`comments-preview-${post.id}`}
        >
          {preview.map((c) => (
            <li
              key={c.id}
              className="text-sm select-none"
              data-testid={`comment-preview-${c.id}`}
              {...bindLongPress(c)}
            >
              <SwipeToRevealDelete
                enabled={canSwipeDelete(c)}
                onDelete={() => removeComment(c)}
              >
                <div className="flex items-start gap-2 bg-transparent py-0.5">
                  <Link to={`/players/${c.author.uid}`} className="flex-shrink-0">
                    <img
                      src={resolveImageUrl(c.author.profilePictureUrl) || DEFAULT_AVATAR}
                      alt={c.author.name || 'Player'}
                      className="w-7 h-7 rounded-full object-cover"
                    />
                  </Link>
                  <div className="flex-1 bg-gray-100 rounded-2xl px-3 py-1.5">
                    <Link
                      to={`/players/${c.author.uid}`}
                      className="font-semibold text-gray-800 hover:text-disc-green text-xs"
                    >
                      {c.author.name || 'Player'}
                    </Link>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">
                      {c.body}
                    </p>
                    <div className="mt-1">{renderCommentNice(c)}</div>
                  </div>
                  {canDelete(c) && (
                    <CommentActionsMenu
                      comment={c}
                      onDelete={() => setPendingDelete(c)}
                    />
                  )}
                </div>
              </SwipeToRevealDelete>
            </li>
          ))}
          {count > preview.length && (
            <li>
              <button
                type="button"
                onClick={openComments}
                className="text-xs text-disc-green font-semibold hover:underline"
                data-testid={`comments-view-more-${post.id}`}
              >
                View all {count} comments
              </button>
            </li>
          )}
        </ul>
      )}

      <div className="flex items-center gap-4 text-sm">
        <button
          type="button"
          onClick={toggleUp}
          className={`flex items-center gap-1.5 font-bold transition rounded-full px-3 py-1 ${
            react.liked
              ? 'bg-disc-green text-white shadow-sm hover:bg-disc-green/90'
              : 'bg-gray-100 text-gray-700 hover:bg-disc-green hover:text-white'
          }`}
          data-testid={`nice-btn-${post.id}`}
          aria-pressed={react.liked}
        >
          <span aria-hidden="true">👍</span>
          <span>{isReview ? 'Up' : (react.liked ? 'Nice ✓' : 'Nice')}</span>
          {react.up > 0 && (
            <span className={`text-xs font-normal ${react.liked ? 'text-white/80' : 'text-gray-500'}`}>
              ({react.up})
            </span>
          )}
        </button>
        {isReview && (
          <button
            type="button"
            onClick={toggleDown}
            className={`flex items-center gap-1 font-semibold transition ${
              react.disliked
                ? 'text-red-600 hover:text-red-500'
                : 'text-gray-500 hover:text-red-600'
            }`}
            data-testid={`down-btn-${post.id}`}
            aria-pressed={react.disliked}
          >
            <span aria-hidden="true">👎</span>
            <span>Down</span>
            {react.down > 0 && (
              <span className="text-xs text-gray-500 font-normal">({react.down})</span>
            )}
          </button>
        )}
        <button
          type="button"
          onClick={openComments}
          className="flex items-center gap-1 text-gray-500 hover:text-disc-green font-semibold transition"
          data-testid={`comments-toggle-${post.id}`}
        >
          💬 <span>Comments</span>
          {count > 0 && <span className="text-xs text-gray-500 font-normal">({count})</span>}
        </button>
      </div>

      {showComments && (
        <div className="mt-3" data-testid={`comments-section-${post.id}`}>          {comments === null ? (
            <p className="text-xs text-gray-400 italic">Loading comments…</p>
          ) : (
            <ul className="space-y-2 mb-3">
              {comments.length === 0 && (
                <li className="text-xs text-gray-400 italic">
                  No comments yet — be the first!
                </li>
              )}
              {comments.map((c) => (
                <li
                  key={c.id}
                  className="text-sm select-none"
                  data-testid={`comment-${c.id}`}
                  {...bindLongPress(c)}
                >
                  <SwipeToRevealDelete
                    enabled={canSwipeDelete(c)}
                    onDelete={() => removeComment(c)}
                  >
                    <div className="flex items-start gap-2 bg-transparent py-0.5">
                      <Link to={`/players/${c.author.uid}`} className="flex-shrink-0">
                        <img
                          src={resolveImageUrl(c.author.profilePictureUrl) || DEFAULT_AVATAR}
                          alt={c.author.name || 'Player'}
                          className="w-7 h-7 rounded-full object-cover"
                        />
                      </Link>
                      <div className="flex-1 bg-gray-100 rounded-2xl px-3 py-1.5">
                        <Link
                          to={`/players/${c.author.uid}`}
                          className="font-semibold text-gray-800 hover:text-disc-green text-xs"
                        >
                          {c.author.name || 'Player'}
                        </Link>
                        <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">
                          {c.body}
                        </p>
                        <div className="mt-1">{renderCommentNice(c)}</div>
                      </div>
                      {canDelete(c) && (
                        <CommentActionsMenu
                          comment={c}
                          onDelete={() => setPendingDelete(c)}
                        />
                      )}
                    </div>
                  </SwipeToRevealDelete>
                </li>
              ))}
            </ul>
          )}

          <form
            onSubmit={submitComment}
            className="flex gap-2"
            data-testid={`comment-form-${post.id}`}
          >
            <input
              type="text"
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Write a comment…"
              maxLength={500}
              className="flex-1 border border-gray-300 rounded-full px-3 py-1.5 text-sm focus:outline-none focus:border-disc-green"
              data-testid={`comment-input-${post.id}`}
            />
            <button
              type="button"
              onClick={insertNicePhrase}
              className="text-disc-green hover:text-disc-green/80 font-semibold text-sm px-2"
              data-testid={`comment-insert-nice-${post.id}`}
              title="Insert a quick Nice!"
            >
              👍 Nice!
            </button>
            <button
              type="submit"
              disabled={submitting || !commentText.trim()}
              className="bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white text-sm font-semibold px-4 py-1.5 rounded-full transition"
              data-testid={`comment-submit-${post.id}`}
            >
              Post
            </button>
          </form>
        </div>
      )}
      {/* Confirmation sheet — mobile-first bottom drawer that swaps to
          a centered modal on ≥ sm. Rendered here so it's a sibling of
          every comment list (preview + expanded thread) and can be
          driven by either. */}
      <ConfirmDeleteCommentSheet
        open={!!pendingDelete}
        onCancel={() => setPendingDelete(null)}
        onConfirm={confirmPendingDelete}
      />
    </div>
  );
}
