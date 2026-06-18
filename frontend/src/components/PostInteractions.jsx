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
  const [nice, setNice] = useState({
    liked: !!post.liked_by_me,
    count: post.nice_count || 0,
  });
  const [showComments, setShowComments] = useState(false);
  const [comments, setComments] = useState(null); // null = not loaded yet
  const [commentText, setCommentText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [count, setCount] = useState(post.comment_count || 0);

  const toggleNice = async () => {
    const prev = nice;
    const optimistic = {
      liked: !prev.liked,
      count: prev.count + (prev.liked ? -1 : 1),
    };
    setNice(optimistic);
    try {
      const res = await api.post(`/posts/${post.id}/nice`);
      setNice({ liked: res.data.liked_by_me, count: res.data.nice_count });
    } catch (err) {
      console.error('toggleNice failed', err);
      setNice(prev);
    }
  };

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
    } catch (err) {
      console.error('delete comment failed', err);
    }
  };

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <div className="flex items-center gap-4 text-sm">
        <button
          type="button"
          onClick={toggleNice}
          className={`flex items-center gap-1 font-semibold transition ${
            nice.liked
              ? 'text-disc-gold hover:text-disc-gold/80'
              : 'text-gray-500 hover:text-disc-gold'
          }`}
          data-testid={`nice-btn-${post.id}`}
          aria-pressed={nice.liked}
        >
          <span aria-hidden="true">{nice.liked ? '👍' : '👍🏻'}</span>
          <span>{nice.liked ? 'Nice ✓' : 'Nice'}</span>
          {nice.count > 0 && (
            <span className="text-xs text-gray-500 font-normal">({nice.count})</span>
          )}
        </button>
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
