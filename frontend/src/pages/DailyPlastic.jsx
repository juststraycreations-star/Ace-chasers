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

const SOURCE_FILTERS = ['All', 'Ultiworld Disc Golf', 'PDGA', 'r/discgolf'];

/**
 * DailyPlastic
 *
 * Full-page disc golf news view backed by the same `/api/news` endpoint that
 * powers the Feed page's news rail. Surfaces up to 24 of the freshest items
 * across Ultiworld, PDGA, and r/discgolf with a one-tap source filter at
 * the top.
 */
export default function DailyPlastic() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fetchedAt, setFetchedAt] = useState(null);
  const [sourceFilter, setSourceFilter] = useState('All');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get('/news', { params: { limit: 24 } });
        if (cancelled) return;
        setItems(res.data?.items || []);
        setFetchedAt(res.data?.fetched_at || null);
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

  const visible =
    sourceFilter === 'All'
      ? items
      : items.filter((i) => i.source === sourceFilter);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8" data-testid="daily-plastic-view">
      <header className="mb-6">
        <h1 className="text-4xl font-bold text-disc-green flex items-center gap-2">
          <span aria-hidden="true">📰</span> Daily Plastic
        </h1>
        <p className="text-gray-600 mt-1">
          Top trending disc golf news, refreshed every 30 minutes.
        </p>
        {fetchedAt && (
          <p className="text-xs text-gray-400 mt-1" data-testid="daily-plastic-fetched-at">
            Updated {timeAgo(fetchedAt)}
          </p>
        )}
      </header>

      <div
        className="flex flex-wrap items-center gap-2 mb-6"
        data-testid="daily-plastic-source-filter"
      >
        {SOURCE_FILTERS.map((src) => {
          const active = sourceFilter === src;
          return (
            <button
              key={src}
              type="button"
              onClick={() => setSourceFilter(src)}
              className={
                active
                  ? 'bg-disc-green text-white font-bold text-sm px-3 py-1.5 rounded-full shadow'
                  : 'border border-disc-green text-disc-green hover:bg-disc-green/10 font-semibold text-sm px-3 py-1.5 rounded-full'
              }
              data-testid={`daily-plastic-source-${src.replace(/[^a-z0-9]/gi, '').toLowerCase() || 'all'}`}
            >
              {src}
            </button>
          );
        })}
      </div>

      {loading ? (
        <p className="text-gray-500" data-testid="daily-plastic-loading">Loading the latest…</p>
      ) : error ? (
        <p className="text-red-600" data-testid="daily-plastic-error">{error}</p>
      ) : visible.length === 0 ? (
        <p className="text-gray-500" data-testid="daily-plastic-empty">
          No stories from {sourceFilter} right now — check back soon.
        </p>
      ) : (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="daily-plastic-list">
          {visible.map((item, idx) => (
            <li key={item.url || idx}>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block bg-white rounded-2xl shadow-sm hover:shadow-md hover:ring-2 hover:ring-disc-green/40 transition p-5 h-full"
                data-testid={`daily-plastic-item-${idx}`}
              >
                <p className="text-[10px] uppercase tracking-wide text-disc-gold font-bold">
                  {item.source}
                </p>
                <h2 className="text-base font-bold text-gray-800 mt-1 line-clamp-3">
                  {item.title}
                </h2>
                {item.summary && (
                  <p className="text-sm text-gray-600 mt-2 line-clamp-3">{item.summary}</p>
                )}
                <div className="flex items-center justify-between mt-3">
                  {item.published_at ? (
                    <span className="text-[11px] text-gray-400">{timeAgo(item.published_at)}</span>
                  ) : <span />}
                  <span className="text-xs font-semibold text-disc-green">Read →</span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
