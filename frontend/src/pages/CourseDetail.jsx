import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

function timeAgo(iso) {
  if (!iso) return '';
  const now = new Date();
  const then = new Date(iso);
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function StarPicker({ value, onChange, disabled }) {
  return (
    <div className="flex gap-1" data-testid="course-review-star-picker">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          disabled={disabled}
          onClick={() => onChange(n)}
          className={`text-3xl leading-none transition ${
            n <= value ? 'text-disc-gold' : 'text-gray-300 hover:text-disc-gold/60'
          }`}
          aria-label={`${n} star${n === 1 ? '' : 's'}`}
          data-testid={`course-review-star-${n}`}
        >
          ★
        </button>
      ))}
    </div>
  );
}

function ReadOnlyStars({ value }) {
  const full = Math.round(value || 0);
  return (
    <span className="text-disc-gold font-bold" aria-label={`${value}/5`}>
      {'★'.repeat(full)}
      <span className="text-gray-300">{'★'.repeat(5 - full)}</span>
    </span>
  );
}

export default function CourseDetail() {
  const { id } = useParams();
  const [course, setCourse] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // New-review form state.
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const fetchAll = async () => {
    try {
      const [c, r] = await Promise.all([
        api.get(`/courses/${id}`),
        api.get(`/courses/${id}/reviews`, { params: { limit: 10 } }),
      ]);
      setCourse(c.data);
      setReviews(r.data || []);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not load course');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, [id]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (rating < 1 || !body.trim()) {
      setFormError('Pick a star rating and write a quick review.');
      return;
    }
    setSubmitting(true);
    setFormError('');
    try {
      const res = await api.post(`/courses/${id}/reviews`, { rating, body: body.trim() });
      const newReview = res.data;
      // Replace any existing review by the same user, otherwise prepend.
      setReviews((prev) => {
        const filtered = (prev || []).filter((r) => r.author?.uid !== newReview.author?.uid);
        return [newReview, ...filtered].slice(0, 10);
      });
      setBody('');
      setRating(0);
      // Refresh course stats so avg_rating + review_count update.
      const c = await api.get(`/courses/${id}`);
      setCourse(c.data);
    } catch (err) {
      setFormError(err?.response?.data?.detail || err.message || 'Could not save your review.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (reviewId) => {
    if (!window.confirm('Delete this review?')) return;
    try {
      await api.delete(`/courses/${id}/reviews/${reviewId}`);
      setReviews((prev) => (prev || []).filter((r) => r.id !== reviewId));
      const c = await api.get(`/courses/${id}`);
      setCourse(c.data);
    } catch (err) {
      console.error('delete review failed', err);
    }
  };

  if (loading) {
    return <div className="max-w-3xl mx-auto px-4 py-12 text-gray-500" data-testid="course-loading">Loading course…</div>;
  }
  if (error || !course) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12" data-testid="course-error">
        <Link to="/courses" className="text-disc-green font-semibold hover:underline">← Back to Courses</Link>
        <p className="text-red-600 mt-4">{error || 'Course not found.'}</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8" data-testid="course-detail-view">
      <Link to="/courses" className="text-disc-green font-semibold hover:underline" data-testid="course-back-link">
        ← Back to Courses
      </Link>

      <header className="bg-white rounded-2xl shadow p-6 mt-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl font-bold text-disc-green" data-testid="course-name">{course.name}</h1>
            {course.location && (
              <p className="text-gray-600 mt-1">📍 {course.location}</p>
            )}
          </div>
          {course.aceClub && (
            <span
              className="flex-shrink-0 bg-disc-gold/15 text-disc-gold border border-disc-gold/40 text-sm font-bold px-3 py-1.5 rounded-full"
              data-testid="course-ace-club-badge"
            >
              🏆 Ace Club{course.aceClubCount != null ? ` (${course.aceClubCount})` : ''}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4 mt-3 text-sm text-gray-700">
          {course.holes && <span>⛳ {course.holes} holes</span>}
          {course.review_count > 0 && (
            <span className="flex items-center gap-1" data-testid="course-avg-rating">
              <ReadOnlyStars value={course.avg_rating} />
              <span className="text-gray-500">({course.review_count} review{course.review_count === 1 ? '' : 's'})</span>
            </span>
          )}
        </div>
        {course.description && (
          <p className="text-gray-700 mt-4">{course.description}</p>
        )}
        {course.submitted_by_name && (
          <p
            className="mt-3 text-sm text-disc-green/80 italic"
            data-testid="course-submitter"
          >
            🥏 Suggested by {course.submitted_by_name}
          </p>
        )}
      </header>

      {/* Write a review */}
      <section className="bg-white rounded-2xl shadow p-6 mt-6" data-testid="course-review-form-card">
        <h2 className="text-lg font-bold text-gray-800 mb-3">Leave a review</h2>
        <form onSubmit={handleSubmit} className="space-y-3" data-testid="course-review-form">
          <StarPicker value={rating} onChange={setRating} disabled={submitting} />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="How did it play? Any tips for first-timers?"
            maxLength={1000}
            rows={3}
            className="w-full border-2 border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green resize-none"
            data-testid="course-review-input"
            disabled={submitting}
          />
          {formError && (
            <p className="text-sm text-red-600" data-testid="course-review-error">{formError}</p>
          )}
          <button
            type="submit"
            disabled={submitting || rating < 1 || !body.trim()}
            className="bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white font-bold px-5 py-2 rounded-lg transition"
            data-testid="course-review-submit"
          >
            {submitting ? 'Posting…' : 'Post review'}
          </button>
          <p className="text-xs text-gray-500">
            You can only have one review per course. Posting again replaces your previous review.
          </p>
        </form>
      </section>

      {/* Recent reviews */}
      <section className="mt-6">
        <h2 className="text-xl font-bold text-gray-800 mb-3">
          {reviews.length === 0 ? 'No reviews yet' : `Recent reviews (last ${reviews.length})`}
        </h2>
        {reviews.length === 0 ? (
          <p className="text-sm text-gray-500">Be the first to share what you thought of {course.name}.</p>
        ) : (
          <ul className="space-y-3" data-testid="course-reviews-list">
            {reviews.map((r) => (
              <li
                key={r.id}
                className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4"
                data-testid={`course-review-${r.id}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <img
                    src={resolveImageUrl(r.author?.profilePictureUrl) || DEFAULT_AVATAR}
                    alt={r.author?.name || 'Player'}
                    className="w-9 h-9 rounded-full object-cover"
                  />
                  <Link
                    to={`/players/${r.author?.uid}`}
                    className="font-semibold text-gray-800 hover:text-disc-green text-sm"
                  >
                    {r.author?.name || 'Player'}
                  </Link>
                  <span className="text-xs text-gray-400 ml-auto">{timeAgo(r.created_at)}</span>
                </div>
                <ReadOnlyStars value={r.rating} />
                <p className="text-gray-700 mt-1 whitespace-pre-wrap">{r.body}</p>
                {r.is_mine && (
                  <button
                    type="button"
                    onClick={() => handleDelete(r.id)}
                    className="text-xs text-red-600 hover:text-red-700 font-semibold mt-2"
                    data-testid={`course-review-delete-${r.id}`}
                  >
                    Delete
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
