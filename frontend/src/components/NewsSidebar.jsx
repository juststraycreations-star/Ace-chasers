import { useEffect, useState } from 'react';
import { api } from '../lib/api';

function timeAgo(iso) {
  if (!iso) return '';
  const now = new Date();
  const then = new Date(iso);
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / 604800)}w ago`;
}

/**
 * NewsSidebar
 *
 * Compact rail of top trending disc golf news pulled from Ultiworld Disc
 * Golf, PDGA News, and r/discgolf. Backend caches the merged feed for 30
 * minutes so we never hammer the upstream RSS endpoints.
 *
 * Designed to live in the right margin of the Feed page on `xl+` screens
 * and gracefully wrap below the feed on smaller viewports.
 */
export default function NewsSidebar() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get('/news', { params: { limit: 10 } });
        if (!cancelled) setItems(res.data?.items || []);
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || err.message || 'Could not load news');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <aside
      className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden"
      data-testid="news-sidebar"
    >
      <header className="px-4 py-3 bg-gradient-to-r from-disc-green/10 to-disc-gold/10 border-b border-gray-100">
        <h2 className="text-lg font-bold text-disc-green flex items-center gap-2">
          <span aria-hidden="true">📰</span> Disc Golf News
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">Top trending stories this week</p>
      </header>

      {loading ? (
        <p className="px-4 py-6 text-sm text-gray-500" data-testid="news-loading">Loading news…</p>
      ) : error ? (
        <p className="px-4 py-6 text-sm text-red-600" data-testid="news-error">{error}</p>
      ) : items.length === 0 ? (
        <p className="px-4 py-6 text-sm text-gray-500" data-testid="news-empty">
          No news right now — check back soon.
        </p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {items.map((item, idx) => (
            <li key={item.url || idx}>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex gap-3 px-4 py-3 hover:bg-disc-green/5 transition"
                data-testid={`news-item-${idx}`}
              >
                {item.thumbnail_url && (
                  <img
                    src={item.thumbnail_url}
                    alt=""
                    loading="lazy"
                    className="w-14 h-14 rounded-lg object-cover flex-shrink-0"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                    }}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] uppercase tracking-wide text-disc-gold font-bold">
                    {item.source}
                  </p>
                  <p className="text-sm font-semibold text-gray-800 mt-0.5 line-clamp-2">
                    {item.title}
                  </p>
                  {item.published_at && (
                    <p className="text-[10px] text-gray-400 mt-1">{timeAgo(item.published_at)}</p>
                  )}
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
