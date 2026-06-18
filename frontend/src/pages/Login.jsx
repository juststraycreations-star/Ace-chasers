import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  signInWithEmailAndPassword,
  signInWithPopup,
} from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { firebaseConfigured, getFirebaseAuth, googleProvider } from '../lib/firebase';
import { clearDevSession, makeDevSession } from '../lib/devAuth';
import { api } from '../lib/api';
import CacheNotice from '../components/CacheNotice';
import DiscIcon from '../components/DiscIcon';

/**
 * Surface a friendlier hint when Firebase or our backend throws a generic
 * "network error" — these almost always mean stale cache or an interrupted
 * sign-in popup. Without this hint users assume the site itself is broken.
 */
function friendlyError(err) {
  const code = err?.code || '';
  const raw = err?.message || err?.response?.data?.detail || '';
  const text = `${code} ${raw}`.toLowerCase();
  if (text.includes('network') || text.includes('failed to fetch')) {
    return 'Network error. Your browser may be caching an older version of the site — try an incognito window, or clear site data and reload. If that still fails, give it a minute and try again.';
  }
  return raw || 'Login failed';
}

export default function Login() {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);
  const setProfile = useAuthStore((s) => s.setProfile);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  /**
   * Run /api/auth/sync and commit the session only on success. The local
   * Firebase session / dev token has already been established by the caller
   * so the API client can attach the right Authorization header.
   */
  const commitSession = async (userObj) => {
    try {
      const sync = await api.post('/auth/sync', {});
      setUser(userObj);
      setProfile(sync.data);
      navigate('/feed');
      return true;
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setError(
        typeof detail === 'string' && detail.toLowerCase().includes('invite')
          ? `${detail} If you don't have an account yet, use the Sign up page instead — invite codes are entered there.`
          : detail
      );
      if (!firebaseConfigured) {
        clearDevSession();
      } else {
        try {
          await getFirebaseAuth().signOut();
        } catch {
          /* noop */
        }
      }
      return false;
    }
  };

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    setError('');
    if (!email || !password) {
      setError('Please fill in all fields');
      return;
    }
    setLoading(true);
    try {
      if (firebaseConfigured) {
        const auth = getFirebaseAuth();
        const cred = await signInWithEmailAndPassword(auth, email, password);
        await commitSession({
          uid: cred.user.uid,
          email: cred.user.email,
          name: cred.user.displayName,
          photoURL: cred.user.photoURL,
        });
      } else {
        const { user } = makeDevSession({ email });
        await commitSession(user);
      }
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError('');
    setLoading(true);
    try {
      if (!firebaseConfigured) {
        setError('Google sign-in requires Firebase to be configured (add REACT_APP_FIREBASE_* env vars).');
        return;
      }
      const auth = getFirebaseAuth();
      const cred = await signInWithPopup(auth, googleProvider);
      await commitSession({
        uid: cred.user.uid,
        email: cred.user.email,
        name: cred.user.displayName,
        photoURL: cred.user.photoURL,
      });
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-disc-green via-disc-purple to-disc-gold flex items-center justify-center px-4">
      <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-disc-green mb-2 flex items-center justify-center gap-2">
            <DiscIcon className="h-9 w-9" />
            <span>Ace Chasers</span>
          </h1>
          <p className="text-gray-600">Connect with local players</p>
        </div>

        <form onSubmit={handleEmailLogin} className="space-y-4" data-testid="login-form">
          <CacheNotice />
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded" data-testid="login-error">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="you@example.com"
              data-testid="login-email-input"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="••••••••"
              data-testid="login-password-input"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-disc-green hover:bg-disc-green/90 text-white font-bold py-3 rounded-lg transition disabled:opacity-50"
            data-testid="login-submit-btn"
          >
            {loading ? 'Signing in…' : 'Login'}
          </button>
        </form>

        <div className="my-4 flex items-center gap-3">
          <div className="flex-1 h-px bg-gray-200" />
          <span className="text-xs uppercase tracking-wide text-gray-400">or</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        <button
          type="button"
          onClick={handleGoogleLogin}
          disabled={loading}
          className="w-full border-2 border-gray-300 hover:border-disc-green bg-white text-gray-800 font-semibold py-3 rounded-lg transition flex items-center justify-center gap-2 disabled:opacity-50"
          data-testid="login-google-btn"
        >
          <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.6 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.3-.4-3.5z"/>
            <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.6 8.4 6.3 14.7z"/>
            <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.3l-6.2-5.2C29.2 35 26.7 36 24 36c-5.3 0-9.7-3.4-11.3-8l-6.5 5C9.4 39.6 16.1 44 24 44z"/>
            <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.3 4.1-4.1 5.5l6.2 5.2c-.4.4 6.6-4.8 6.6-14.7 0-1.2-.1-2.3-.4-3.5z"/>
          </svg>
          Continue with Google
        </button>

        <div className="mt-6 text-center">
          <p className="text-gray-600">
            Don&apos;t have an account?{' '}
            <Link to="/signup" className="text-disc-green hover:underline font-semibold" data-testid="login-signup-link">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
