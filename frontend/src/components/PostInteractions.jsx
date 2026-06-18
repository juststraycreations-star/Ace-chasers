import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

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

  const deleteMyComment = async (commentId) => {
    try {
      await api.delete(`/posts/${post.id}/comments/${commentId}`);
      setComments((prev) => (prev || []).filter((c) => c.id !== commentId));
      setCount((c) => Math.max(0, c - 1));
      setPreview((prev) => prev.filter((c) => c.id !== commentId));
    } catch (err) {
      console.error('delete comment failed', err);
    }
  };

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
              className="flex items-start gap-2 text-sm"
              data-testid={`comment-preview-${c.id}`}
            >
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
              </div>
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
        <div className="mt-3" data-testid={`comments-section-${post.id}`}>
          {comments === null ? (
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
                  className="flex items-start gap-2 text-sm"
                  data-testid={`comment-${c.id}`}
                >
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
                  </div>
                  {c.is_mine && (
                    <button
                      type="button"
                      onClick={() => deleteMyComment(c.id)}
                      className="text-xs text-gray-400 hover:text-red-500"
                      title="Delete comment"
                      data-testid={`comment-delete-${c.id}`}
                      aria-label="Delete comment"
                    >
                      ✕
                    </button>
                  )}
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
    </div>
  );
}
