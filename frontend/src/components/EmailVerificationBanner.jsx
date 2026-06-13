import { useState } from 'react';
import { sendEmailVerification } from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { firebaseConfigured, getFirebaseAuth } from '../lib/firebase';

/**
 * Soft banner that nudges unverified users to verify their email. Renders
 * nothing when the profile is verified, missing, or when the app is running
 * in dev mode (no Firebase) — verification doesn't apply there.
 */
export default function EmailVerificationBanner() {
  const profile = useAuthStore((s) => s.profile);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  if (!firebaseConfigured) return null;
  if (!profile) return null;
  if (profile.emailVerified) return null;

  const handleResend = async () => {
    setError('');
    setSending(true);
    try {
      const auth = getFirebaseAuth();
      const user = auth?.currentUser;
      if (!user) throw new Error('No active session');
      await sendEmailVerification(user);
      setSent(true);
    } catch (err) {
      setError(err?.message || 'Could not send verification email');
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="bg-yellow-100 border-b border-yellow-300 text-yellow-900"
      data-testid="email-verification-banner"
      role="status"
    >
      <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-sm">
        <div>
          <span className="font-semibold">Verify your email</span>{' '}
          to unlock all features. We sent a link to{' '}
          <span className="font-mono">{profile.email}</span> when you signed up.
        </div>
        <div className="flex items-center gap-3">
          {error && (
            <span className="text-red-700" data-testid="verify-error">
              {error}
            </span>
          )}
          {sent ? (
            <span className="text-green-700 font-semibold" data-testid="verify-sent">
              Verification email sent ✓
            </span>
          ) : (
            <button
              type="button"
              onClick={handleResend}
              disabled={sending}
              className="bg-yellow-300 hover:bg-yellow-400 text-yellow-900 font-semibold px-3 py-1 rounded transition disabled:opacity-60"
              data-testid="verify-resend-btn"
            >
              {sending ? 'Sending…' : 'Resend email'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
