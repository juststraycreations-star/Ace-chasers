import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { api } from '../lib/api';
import { compressImage } from '../lib/compressImage';
import { resolveImageUrl } from '../lib/images';

/**
 * OnboardingGate
 *
 * Two-step blocking onboarding flow that mounts above every authenticated
 * route until the user has at least set a name. Step 1 is required, step 2
 * (profile photo) is optional and can be skipped.
 *
 *   step "name":  blocking name input — cannot be skipped.
 *   step "photo": optional photo upload that follows immediately after name
 *                 save. Has a Skip button that closes the gate without an
 *                 upload.
 *
 * Once dismissed (name saved + photo done/skipped), the gate marks itself
 * complete in sessionStorage so a quick re-render doesn't bounce the user
 * back to step 2. Re-fires on fresh login if profile.name is still empty.
 */
const PHOTO_STEP_DONE_KEY = 'ace_onboarding_photo_step_done';
const MAX_RAW_BYTES = 30 * 1024 * 1024;

export default function OnboardingGate() {
  const profile = useAuthStore((s) => s.profile);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authReady = useAuthStore((s) => s.authReady);
  const patchProfile = useAuthStore((s) => s.patchProfile);

  const [step, setStep] = useState('name'); // 'name' | 'photo'
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // Photo step state.
  const [preview, setPreview] = useState(null); // local data URL
  const [uploading, setUploading] = useState(false);
  const [photoStepDone, setPhotoStepDone] = useState(() => {
    try {
      return sessionStorage.getItem(PHOTO_STEP_DONE_KEY) === '1';
    } catch (_e) {
      return false;
    }
  });
  const fileInputRef = useRef(null);

  // Reset local state when the underlying profile changes (e.g. re-auth).
  useEffect(() => {
    setName('');
    setError('');
    setPreview(null);
  }, [profile?.uid]);

  // Gate criteria.
  const hasName = !!(profile?.name && profile.name.trim());
  const needsName = authReady && isAuthenticated && profile && !hasName;
  const needsPhoto =
    authReady && isAuthenticated && profile && hasName && !profile.profilePictureUrl && !photoStepDone;

  // Drive the current step from the underlying state.
  useEffect(() => {
    if (needsName) setStep('name');
    else if (needsPhoto) setStep('photo');
  }, [needsName, needsPhoto]);

  if (!needsName && !needsPhoto) return null;

  const closePhotoStep = () => {
    try {
      sessionStorage.setItem(PHOTO_STEP_DONE_KEY, '1');
    } catch (_e) {
      /* sessionStorage disabled — non-blocking */
    }
    setPhotoStepDone(true);
  };

  const handleNameSubmit = async (e) => {
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
      // The needsPhoto computed flag will flip the step automatically.
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not save your name. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handlePhotoPick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_RAW_BYTES) {
      setError('Image is too large — please pick something under 30 MB.');
      return;
    }
    setError('');
    setUploading(true);
    try {
      const compressed = await compressImage(file, { maxDim: 1024 });
      const reader = new FileReader();
      reader.onload = () => setPreview(reader.result);
      reader.readAsDataURL(compressed);
      const form = new FormData();
      form.append('image', compressed, compressed.name || 'photo.jpg');
      const res = await api.post('/users/me/profile-picture', form);
      patchProfile({ profilePictureUrl: res.data.profilePictureUrl });
      closePhotoStep();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Photo upload failed. Try a different image.');
      setPreview(null);
    } finally {
      setUploading(false);
      // Reset the input so picking the same file again still fires onChange.
      if (fileInputRef.current) fileInputRef.current.value = '';
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
            <span aria-hidden="true">🥏</span>
            {step === 'name' ? 'Welcome to Ace Chasers!' : 'Add a profile photo'}
          </h2>
          <p className="text-white/90 text-sm mt-1">
            {step === 'name'
              ? 'What should other players call you?'
              : "Players with a photo get 3x more replies. You can skip and add one later."}
          </p>
          {/* Tiny step indicator */}
          <div className="mt-3 flex items-center gap-2" data-testid="onboarding-step-indicator">
            <span
              className={`h-1.5 flex-1 rounded-full ${step === 'name' ? 'bg-white' : 'bg-white/60'}`}
              aria-label={step === 'name' ? 'Step 1 of 2 (current)' : 'Step 1 of 2'}
            />
            <span
              className={`h-1.5 flex-1 rounded-full ${step === 'photo' ? 'bg-white' : 'bg-white/30'}`}
              aria-label={step === 'photo' ? 'Step 2 of 2 (current)' : 'Step 2 of 2'}
            />
          </div>
        </div>

        {step === 'name' ? (
          <form onSubmit={handleNameSubmit} className="px-6 py-5 space-y-4">
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
              {saving ? 'Saving…' : 'Next 🥏'}
            </button>
          </form>
        ) : (
          <div className="px-6 py-5 space-y-4">
            <div className="flex flex-col items-center gap-3">
              <div className="w-28 h-28 rounded-full overflow-hidden border-4 border-disc-green/30 bg-gray-100 flex items-center justify-center">
                {preview || profile?.profilePictureUrl ? (
                  <img
                    src={preview || resolveImageUrl(profile?.profilePictureUrl)}
                    alt="Your profile"
                    className="w-full h-full object-cover"
                    data-testid="onboarding-photo-preview"
                  />
                ) : (
                  <span className="text-4xl" aria-hidden="true">🥏</span>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handlePhotoPick}
                className="hidden"
                data-testid="onboarding-photo-input"
                disabled={uploading}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="w-full bg-disc-green hover:bg-disc-green/90 disabled:opacity-50 text-white font-bold py-3 rounded-lg transition shadow-md"
                data-testid="onboarding-photo-pick-btn"
              >
                {uploading ? 'Uploading…' : '📷 Pick a photo'}
              </button>
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
              type="button"
              onClick={closePhotoStep}
              disabled={uploading}
              className="w-full text-gray-600 hover:text-gray-900 font-semibold py-2 transition"
              data-testid="onboarding-photo-skip-btn"
            >
              Skip for now
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
