import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import PublicProfilePreview from '../components/PublicProfilePreview';

/**
 * Public read-only view of any user's profile, reached via /players/:uid.
 * The current logged-in user uses /profile for their own (editable) view.
 */
export default function PlayerProfile() {
  const { uid } = useParams();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await api.get(`/users/${uid}`);
        if (!cancelled) setProfile(res.data);
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [uid]);

  return (
    <div className="max-w-2xl mx-auto px-4 py-8" data-testid="player-profile-view">
      <Link
        to="/feed"
        className="text-sm text-disc-green hover:underline mb-4 inline-block"
        data-testid="player-profile-back"
      >
        ← Back to Feed
      </Link>

      {loading ? (
        <p className="text-center text-gray-500" data-testid="player-profile-loading">
          Loading profile…
        </p>
      ) : error ? (
        <div
          className="bg-red-50 border-2 border-red-300 text-red-800 rounded-lg p-4"
          data-testid="player-profile-error"
        >
          {error}
        </div>
      ) : profile ? (
        <PublicProfilePreview player={profile} />
      ) : null}
    </div>
  );
}
