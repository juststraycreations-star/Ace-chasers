import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuthStore } from '../store/authStore';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import PostInteractions from '../components/PostInteractions';

const PLACEHOLDER =
  'Leopard3 7|5|-2|1 a versatile, understable fairway driver beloved for its smooth flight and easy-to-control distance. As a flatter, faster evolution of the classic Leopard, it excels at straight tunnel shots, effortless turnovers, and sweeping hyzer-flips right out of the box.';

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function BagCheck() {
  const profile = useAuthStore((s) => s.profile);
  const [reviews, setReviews] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState('public');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);

  const fetchReviews = async () => {
    setLoading(true);
    try {
      const res = await api.get('/feed', { params: { kind: 'disc_review' } });
      setReviews(res.data.posts || []);
      setNextCursor(res.data.next_cursor);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
  }, []);

  const loadMore = async () => {
    if (!nextCursor) return;
    try {
      const res = await api.get('/feed', { params: { kind: 'disc_review', before: nextCursor } });
      setReviews((prev) => [...prev, ...(res.data.posts || [])]);
      setNextCursor(res.data.next_cursor);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!body.trim()) {
      setError('Add some text about the disc.');
      return;
    }
    setPosting(true);
    try {
      const form = new FormData();
      form.append('body', body);
      form.append('visibility', visibility);
      form.append('kind', 'disc_review');
      const res = await api.post('/posts', form);
      setReviews((prev) => [res.data, ...prev]);
      setBody('');
      setVisibility('public');
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8" data-testid="bagcheck-view">
      <header className="mb-6">
        <h1 className="text-4xl font-bold text-disc-green">🎒 Bag Check</h1>
        <p className="text-sm text-gray-600 mt-1">
          Share disc reviews. Get the community&apos;s thumbs.
        </p>
      </header>

      <form
        ref={formRef}
        onSubmit={submit}
        className="bg-white rounded-2xl shadow-lg p-5 mb-8"
        data-testid="bagcheck-form"
      >
        <div className="flex items-start gap-3">
          <img
            src={resolveImageUrl(profile?.profilePictureUrl) || DEFAULT_AVATAR}
            alt="you"
            className="w-10 h-10 rounded-full object-cover"
          />
          <div className="flex-1">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={PLACEHOLDER}
              rows={4}
              maxLength={1000}
              className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-disc-green resize-y"
              data-testid="bagcheck-body"
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <select
                value={visibility}
                onChange={(e) => setVisibility(e.target.value)}
                className="text-xs border border-gray-200 rounded-md px-2 py-1"
                data-testid="bagcheck-visibility"
              >
                <option value="public">Everyone</option>
                <option value="friends_only">Players only</option>
              </select>
              <button
                type="submit"
                disabled={posting || !body.trim()}
                className="bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white text-sm font-bold px-5 py-1.5 rounded-full transition"
                data-testid="bagcheck-submit"
              >
                {posting ? 'Posting…' : 'Post review'}
              </button>
            </div>
            {error && (
              <p className="text-xs text-red-600 mt-2" data-testid="bagcheck-error">
                {error}
              </p>
            )}
          </div>
        </div>
      </form>

      {loading && reviews.length === 0 ? (
        <p className="text-center text-gray-500" data-testid="bagcheck-loading">
          Loading reviews…
        </p>
      ) : reviews.length === 0 ? (
        <p className="text-center text-gray-500" data-testid="bagcheck-empty">
          No reviews yet — be the first to weigh in on a disc!
        </p>
      ) : (
        <div className="space-y-4">
          {reviews.map((post) => (
            <article
              key={post.id}
              className="bg-white rounded-2xl shadow p-5"
              data-testid={`review-${post.id}`}
            >
              <div className="flex items-center gap-3 mb-3">
                <Link to={`/players/${post.author.uid}`}>
                  <img
                    src={resolveImageUrl(post.author.profilePictureUrl) || DEFAULT_AVATAR}
                    alt={post.author.name || 'Player'}
                    className="w-10 h-10 rounded-full object-cover"
                  />
                </Link>
                <div>
                  <Link
                    to={`/players/${post.author.uid}`}
                    className="font-semibold text-gray-800 hover:text-disc-green text-sm"
                  >
                    {post.author.name || 'Player'}
                  </Link>
                  <p className="text-xs text-gray-500">{timeAgo(post.created_at)}</p>
                </div>
              </div>
              <p
                className="text-gray-800 whitespace-pre-wrap text-sm"
                data-testid={`review-body-${post.id}`}
              >
                {post.body}
              </p>
              <PostInteractions post={post} />
            </article>
          ))}
          {nextCursor && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={loadMore}
                className="border-2 border-disc-green text-disc-green hover:bg-disc-green hover:text-white font-semibold px-6 py-2 rounded-lg transition"
                data-testid="bagcheck-load-more"
              >
                Load more reviews
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
