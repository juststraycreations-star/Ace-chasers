import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
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

function StarRating({ value }) {
  const full = Math.round(value || 0);
  return (
    <span className="text-disc-gold font-bold text-sm" aria-label={`${value}/5`}>
      {'★'.repeat(full)}
      <span className="text-gray-300">{'★'.repeat(5 - full)}</span>
    </span>
  );
}

export default function Courses() {
  const [courses, setCourses] = useState([]);
  const [recent, setRecent] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchCourses = async (q = '') => {
    try {
      const params = q ? { search: q } : {};
      const res = await api.get('/courses', { params });
      setCourses(res.data || []);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not load courses');
    }
  };

  const fetchRecent = async () => {
    try {
      const res = await api.get('/courses/recent-reviews', { params: { limit: 10 } });
      setRecent(res.data || []);
    } catch (err) {
      // Non-critical; show empty.
      console.warn('recent course reviews fetch failed', err);
      setRecent([]);
    }
  };

  useEffect(() => {
    Promise.all([fetchCourses(), fetchRecent()]).finally(() => setLoading(false));
  }, []);

  // Debounced search refetch
  useEffect(() => {
    const t = setTimeout(() => fetchCourses(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="courses-view">
      <header className="mb-6">
        <h1 className="text-4xl font-bold text-disc-green">Courses</h1>
        <p className="text-gray-600 mt-1">
          Browse disc golf courses and see what other Ace Chasers are saying.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main list */}
        <section className="lg:col-span-2" data-testid="courses-list">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or location…"
            className="w-full border-2 border-gray-300 rounded-lg px-3 py-2 mb-4 focus:outline-none focus:border-disc-green"
            data-testid="courses-search"
          />

          {loading ? (
            <p className="text-gray-500">Loading courses…</p>
          ) : error ? (
            <p className="text-red-600">{error}</p>
          ) : courses.length === 0 ? (
            <p className="text-gray-500" data-testid="courses-empty">
              No courses match &ldquo;{search}&rdquo;.
            </p>
          ) : (
            <ul className="space-y-3">
              {courses.map((c) => (
                <li key={c.id}>
                  <Link
                    to={`/courses/${c.id}`}
                    className="block bg-white rounded-2xl shadow hover:shadow-md transition border border-gray-100 p-4"
                    data-testid={`course-card-${c.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <h2 className="text-lg font-bold text-disc-green truncate">
                          {c.name}
                        </h2>
                        {c.location && (
                          <p className="text-sm text-gray-600 truncate">📍 {c.location}</p>
                        )}
                        {c.description && (
                          <p className="text-sm text-gray-700 mt-1 line-clamp-2">{c.description}</p>
                        )}
                        <div className="flex items-center gap-3 mt-2 text-xs text-gray-600">
                          {c.holes && <span>⛳ {c.holes} holes</span>}
                          {c.review_count > 0 && (
                            <span className="flex items-center gap-1">
                              <StarRating value={c.avg_rating} />
                              <span className="text-gray-500">({c.review_count})</span>
                            </span>
                          )}
                        </div>
                      </div>
                      {c.aceClub && (
                        <span
                          className="flex-shrink-0 bg-disc-gold/15 text-disc-gold border border-disc-gold/40 text-xs font-bold px-2 py-1 rounded-full"
                          data-testid={`course-ace-club-${c.id}`}
                          title="This course runs an Ace Club"
                        >
                          🏆 Ace Club{c.aceClubCount != null ? ` (${c.aceClubCount})` : ''}
                        </span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Recent reviews sidebar */}
        <aside data-testid="courses-recent-reviews">
          <h2 className="text-xl font-bold text-gray-800 mb-3">Recent reviews</h2>
          {recent.length === 0 ? (
            <p className="text-sm text-gray-500">
              No reviews yet. Tap a course and drop the first one!
            </p>
          ) : (
            <ul className="space-y-3">
              {recent.map((r) => (
                <li
                  key={r.id}
                  className="bg-white rounded-xl shadow-sm border border-gray-100 p-3 text-sm"
                  data-testid={`recent-review-${r.id}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <img
                      src={resolveImageUrl(r.author?.profilePictureUrl) || DEFAULT_AVATAR}
                      alt={r.author?.name || 'Player'}
                      className="w-7 h-7 rounded-full object-cover"
                    />
                    <Link
                      to={`/players/${r.author?.uid}`}
                      className="font-semibold text-gray-800 hover:text-disc-green text-xs truncate"
                    >
                      {r.author?.name || 'Player'}
                    </Link>
                    <span className="text-[10px] text-gray-400 ml-auto">{timeAgo(r.created_at)}</span>
                  </div>
                  <Link
                    to={`/courses/${r.course_id}`}
                    className="text-xs font-semibold text-disc-green hover:underline block mb-1"
                  >
                    {r.course_name} {r.course_location && <span className="text-gray-500 font-normal">· {r.course_location}</span>}
                  </Link>
                  <StarRating value={r.rating} />
                  <p className="text-gray-700 mt-1 line-clamp-3">{r.body}</p>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}
