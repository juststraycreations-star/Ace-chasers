import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  createUserWithEmailAndPassword,
  sendEmailVerification,
  signInWithPopup,
  updateProfile,
} from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { firebaseConfigured, getFirebaseAuth, googleProvider } from '../lib/firebase';
import { clearDevSession, makeDevSession } from '../lib/devAuth';
import { api } from '../lib/api';
import CacheNotice from '../components/CacheNotice';
import DiscIcon from '../components/DiscIcon';

function friendlyError(err) {
  const code = err?.code || '';
  const raw = err?.message || err?.response?.data?.detail || '';
  const text = `${code} ${raw}`.toLowerCase();
  if (text.includes('network') || text.includes('failed to fetch')) {
    return 'Network error. Your browser may be caching an older version of the site — try an incognito window, or clear site data and reload. If that still fails, give it a minute and try again.';
  }
  return raw || 'Sign up failed';
}

export default function SignUp() {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);
  const setProfile = useAuthStore((s) => s.setProfile);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    age: '',
    skillLevel: 'Beginner',
    inviteCode: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const requireInvite = useAuthStore((s) => s.config.require_invite);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  /**
   * Try /auth/sync (with invite_code), then push the initial profile fields
   * from the form. Only commits the session on success — failure keeps the
   * user on /signup with a visible error.
   */
  const commitSession = async (userObj) => {
    try {
      await api.post('/auth/sync', {
        invite_code: formData.inviteCode ? formData.inviteCode.trim() : undefined,
      });
      const payload = {
        name: formData.name || userObj.name || null,
        age: formData.age ? Number(formData.age) : null,
        skillLevel: formData.skillLevel,
      };
      const updated = await api.put('/users/me', payload);
      setUser(userObj);
      setProfile(updated.data);
      navigate('/feed');
      return true;
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setError(typeof detail === 'string' ? detail : 'Sign up failed');
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

  const handleEmailSignup = async (e) => {
    e.preventDefault();
    setError('');
    if (!formData.name || !formData.email || !formData.password || !formData.age) {
      setError('Please fill in all fields');
      return;
    }
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      if (firebaseConfigured) {
        const auth = getFirebaseAuth();
        const cred = await createUserWithEmailAndPassword(
          auth,
          formData.email,
          formData.password
        );
        if (formData.name) {
          await updateProfile(cred.user, { displayName: formData.name });
        }
        const ok = await commitSession({
          uid: cred.user.uid,
          email: cred.user.email,
          name: formData.name || cred.user.displayName,
          photoURL: cred.user.photoURL,
        });
        if (ok) {
          // Fire the verification email (best-effort; soft banner handles
          // the rest of the lifecycle).
          // Email verification disabled — users sign in immediately.
          // To re-enable: uncomment the block below.
          // try {
          //   await sendEmailVerification(cred.user);
          // } catch (err) {
          //   console.warn('sendEmailVerification failed:', err?.message);
          // }
        }
      } else {
        const { user } = makeDevSession({ email: formData.email, name: formData.name });
        await commitSession(user);
      }
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
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
    <div className="min-h-screen bg-gradient-to-br from-disc-green via-disc-purple to-disc-gold flex items-center justify-center px-4 py-8">
      <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-disc-green mb-2 flex items-center justify-center gap-2">
            <DiscIcon className="h-9 w-9" />
            <span>Ace Chasers</span>
          </h1>
          <p className="text-gray-600">Create your account</p>
        </div>

        <form onSubmit={handleEmailSignup} className="space-y-4" data-testid="signup-form">
          <CacheNotice />
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded" data-testid="signup-error">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Full Name</label>
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="John Doe"
              data-testid="signup-name-input"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Email</label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="you@example.com"
              data-testid="signup-email-input"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Age</label>
            <input
              type="number"
              name="age"
              value={formData.age}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="25"
              data-testid="signup-age-input"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Skill Level</label>
            <select
              name="skillLevel"
              value={formData.skillLevel}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              data-testid="signup-skill-input"
            >
              <option>Beginner</option>
              <option>Intermediate</option>
              <option>Advanced</option>
              <option>Pro</option>
            </select>
          </div>

          {requireInvite && (
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Invite Code</label>
              <input
                type="text"
                name="inviteCode"
                value={formData.inviteCode}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 font-mono uppercase focus:outline-none focus:border-disc-green"
                placeholder="ACE-XXXX-XXXX"
                data-testid="signup-invite-input"
              />
              <p className="text-xs text-gray-500 mt-1">
                Ace Chasers is currently invite-only. Paste the code from your invite.
              </p>
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Password</label>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="••••••••"
              data-testid="signup-password-input"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Confirm Password</label>
            <input
              type="password"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-disc-green"
              placeholder="••••••••"
              data-testid="signup-confirm-password-input"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-disc-green hover:bg-disc-green/90 text-white font-bold py-3 rounded-lg transition disabled:opacity-50"
            data-testid="signup-submit-btn"
          >
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <div className="my-4 flex items-center gap-3">
          <div className="flex-1 h-px bg-gray-200" />
          <span className="text-xs uppercase tracking-wide text-gray-400">or</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        <button
          type="button"
          onClick={handleGoogleSignup}
          disabled={loading}
          className="w-full border-2 border-gray-300 hover:border-disc-green bg-white text-gray-800 font-semibold py-3 rounded-lg transition flex items-center justify-center gap-2 disabled:opacity-50"
          data-testid="signup-google-btn"
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
            Already have an account?{' '}
            <Link to="/login" className="text-disc-green hover:underline font-semibold" data-testid="signup-login-link">
              Login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
