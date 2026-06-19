import { useEffect, useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { api } from '../lib/api';

/**
 * OnboardingGate
 *
 * Blocks every authenticated route until the user has filled in their name.
 * Eliminates the "empty placeholder card" problem at the source: the moment
 * someone signs up, they get this modal. They cannot dismiss it. Once they
 * save a name, the gate closes and the rest of the app becomes available.
 *
 * Mounted once in App.jsx above the routes. The Profile field stays editable
 * later — this only catches the very first save.
 */
export default function OnboardingGate() {
  const profile = useAuthStore((s) => s.profile);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authReady = useAuthStore((s) => s.authReady);
  const patchProfile = useAuthStore((s) => s.patchProfile);

  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Reset the local input whenever the profile loads / changes so we don't
  // carry stale state across re-auth.
  useEffect(() => {
    setName('');
    setError('');
  }, [profile?.uid]);

  // Gate criteria: authed, profile loaded, and the user has no usable name.
  const needsName =
    authReady &&
    isAuthenticated &&
    profile &&
    !(profile.name && profile.name.trim());

  if (!needsName) return null;

  const handleSave = async (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 2) {
      setError('Please use at least 2 characters.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await api.put('/users/me', { name: trimmed });
      patchProfile({ name: res.data.name });
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not save your name. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[90] bg-black/70 flex items-center justify-center p-4"
      data-testid="onboarding-gate"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        <div className="px-6 py-5 bg-gradient-to-r from-disc-green to-disc-gold text-white">
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <span aria-hidden="true">🥏</span> Welcome to Ace Chasers!
          </h2>
          <p className="text-white/90 text-sm mt-1">
            What should other players call you?
          </p>
        </div>

        <form onSubmit={handleSave} className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1" htmlFor="onboarding-name">
              Your name
            </label>
            <input
              id="onboarding-name"
              type="text"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sam Putter"
              maxLength={80}
              className="w-full border-2 border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green text-base"
              data-testid="onboarding-name-input"
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              You can change it any time from your profile. We just need a name to find players for you.
            </p>
          </div>

          {error && (
            <p
              className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
              data-testid="onboarding-error"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={saving || name.trim().length < 2}
            className="w-full bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white font-bold py-3 rounded-lg transition shadow-md"
            data-testid="onboarding-save-btn"
          >
            {saving ? 'Saving…' : "Let's go 🥏"}
          </button>
        </form>
      </div>
    </div>
  );
}
