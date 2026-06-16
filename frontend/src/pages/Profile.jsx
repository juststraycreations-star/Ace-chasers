import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { api } from '../lib/api';
import { compressImage } from '../lib/compressImage';
import { resolveImageUrl } from '../lib/images';
import PublicProfilePreview from '../components/PublicProfilePreview';

const DEFAULT_INTERESTS = ['tournaments', 'hiking', 'casual play'];
const DEFAULT_AVATAR =
  'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop';
const MAX_RAW_BYTES = 30 * 1024 * 1024;

export default function Profile() {
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadingType, setUploadingType] = useState(null); // 'avatar' | 'banner' | null

  const avatarInputRef = useRef(null);
  const bannerInputRef = useRef(null);

  useEffect(() => {
    if (profile) setDraft(profile);
  }, [profile, setDraft]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setDraft((prev) => ({ ...prev, [name]: value }));
  };

  const validateImage = (file) => {
    if (!file) return 'No file selected';
    if (!file.type.startsWith('image/')) return `That doesn't look like an image (${file.type || 'unknown type'}).`;
    if (file.size > MAX_RAW_BYTES) return 'Image is huge (>30MB). Pick a smaller file or take a fresh photo.';
    return null;
  };

  const uploadImage = async (file, kind) => {
    const err = validateImage(file);
    if (err) {
      setUploadError(err);
      return;
    }
    setUploadError('');
    setUploadingType(kind);
    try {
      const compressed = await compressImage(file, kind === 'avatar' ? 'avatar' : 'banner');
      const form = new FormData();
      form.append('image', compressed);
      const endpoint =
        kind === 'avatar' ? '/users/me/profile-picture' : '/users/me/banner';
      const res = await api.post(endpoint, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setProfile(res.data);
    } catch (e) {
      setUploadError(e?.response?.data?.detail || e.message);
    } finally {
      setUploadingType(null);
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    setLoading(true);
    setSaveMessage('');
    try {
      const payload = {
        name: draft.name,
        age: draft.age ? Number(draft.age) : null,
        skillLevel: draft.skillLevel,
        location: draft.location,
        favoriteCourse: draft.favoriteCourse,
        favoriteFrisbee: draft.favoriteFrisbee,
        homeCourse: draft.homeCourse,
        bio: draft.bio,
        interests: draft.interests,
        privacy: draft.privacy || {},
      };
      const res = await api.put('/users/me', payload);
      setProfile(res.data);
      setSaveMessage('Profile saved successfully! ✓');
      setIsEditing(false);
      setTimeout(() => setSaveMessage(''), 3000);
    } catch (err) {
      setSaveMessage(err?.response?.data?.detail || 'Failed to save profile.');
    } finally {
      setLoading(false);
    }
  };

  if (!profile || !draft) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="text-center" data-testid="profile-loading">Loading profile…</div>
      </div>
    );
  }

  // Source-of-truth for the imagery: the saved profile (server state), not the draft.
  const bannerUrl = resolveImageUrl(profile.bannerUrl);
  const avatarUrl = resolveImageUrl(profile.profilePictureUrl) || DEFAULT_AVATAR;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8" data-testid="profile-view">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-disc-green">Your profile</h1>
          <p className="text-sm text-gray-600">
            Banner and thumbnail show up everywhere other players see you.
          </p>
        </div>
        <button
          onClick={() => setIsEditing((v) => !v)}
          className="bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 px-6 rounded-lg transition"
          data-testid={isEditing ? 'profile-cancel-btn' : 'profile-edit-btn'}
        >
          {isEditing ? 'Done editing' : 'Edit Profile'}
        </button>
      </div>

      {saveMessage && (
        <div
          className={`mb-4 px-4 py-3 rounded ${
            saveMessage.includes('successfully')
              ? 'bg-green-100 text-green-700 border border-green-400'
              : 'bg-yellow-100 text-yellow-700 border border-yellow-400'
          }`}
          data-testid="profile-save-message"
        >
          {saveMessage}
        </div>
      )}

      {uploadError && (
        <div
          className="mb-4 flex items-start gap-3 bg-red-50 border-2 border-red-300 rounded-lg px-4 py-3 text-sm text-red-800"
          data-testid="profile-upload-error"
          role="alert"
        >
          <span className="text-lg leading-none" aria-hidden="true">⚠️</span>
          <div className="flex-1">
            <p className="font-semibold">Upload failed</p>
            <p>{uploadError}</p>
          </div>
          <button
            type="button"
            onClick={() => setUploadError('')}
            className="text-red-700 hover:text-red-900 font-bold leading-none"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      {/* Editable banner + avatar surface */}
      <div className="bg-white rounded-2xl shadow-lg overflow-hidden mb-6">
        {/* Banner */}
        <div
          className="relative h-40 bg-gradient-to-r from-disc-green to-disc-purple bg-cover bg-center"
          style={bannerUrl ? { backgroundImage: `url(${bannerUrl})` } : undefined}
          data-testid="profile-banner"
        >
          {uploadingType === 'banner' && (
            <div className="absolute inset-0 bg-black/40 flex items-center justify-center text-white text-sm font-semibold">
              Uploading banner…
            </div>
          )}
          {isEditing && (
            <>
              <input
                ref={bannerInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
                onChange={(e) => uploadImage(e.target.files?.[0], 'banner')}
                className="hidden"
                data-testid="profile-banner-input"
              />
              <button
                type="button"
                onClick={() => bannerInputRef.current?.click()}
                disabled={uploadingType !== null}
                className="absolute top-3 right-3 bg-white/90 hover:bg-white text-disc-green font-semibold px-3 py-1.5 rounded-lg shadow text-sm disabled:opacity-60"
                data-testid="profile-banner-upload-btn"
              >
                📷 {profile.bannerUrl ? 'Change banner' : 'Upload banner'}
              </button>
            </>
          )}
        </div>

        {/* Avatar overlapping banner */}
        <div className="px-6 pb-6 -mt-12">
          <div className="relative inline-block">
            <img
              src={avatarUrl}
              alt="Profile"
              className="w-24 h-24 rounded-full border-4 border-white shadow-lg object-cover bg-gray-200"
              data-testid="profile-thumbnail"
            />
            {uploadingType === 'avatar' && (
              <div className="absolute inset-0 rounded-full bg-black/40 flex items-center justify-center text-white text-xs font-semibold">
                …
              </div>
            )}
            {isEditing && (
              <>
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
                  onChange={(e) => uploadImage(e.target.files?.[0], 'avatar')}
                  className="hidden"
                  data-testid="profile-avatar-input"
                />
                <button
                  type="button"
                  onClick={() => avatarInputRef.current?.click()}
                  disabled={uploadingType !== null}
                  className="absolute bottom-0 right-0 bg-disc-green hover:bg-disc-green/90 text-white rounded-full w-9 h-9 flex items-center justify-center shadow-lg disabled:opacity-60"
                  aria-label="Change profile picture"
                  data-testid="profile-avatar-upload-btn"
                >
                  📷
                </button>
              </>
            )}
          </div>

          <h2 className="mt-3 text-2xl font-bold text-gray-800">
            {profile.name || 'Your name'}
            {profile.age ? `, ${profile.age}` : ''}
          </h2>
          <p className="text-disc-gold font-semibold">{profile.skillLevel || 'Beginner'}</p>
        </div>
      </div>

      {/* Editable fields */}
      {isEditing ? (
        <div className="bg-white rounded-2xl shadow-lg p-6" data-testid="profile-edit-view">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">Name</label>
              <input
                type="text"
                name="name"
                value={draft.name || ''}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                data-testid="profile-name-input"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">Age</label>
              <input
                type="number"
                name="age"
                value={draft.age || ''}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                data-testid="profile-age-input"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">Skill Level</label>
              <select
                name="skillLevel"
                value={draft.skillLevel || 'Beginner'}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                data-testid="profile-skill-input"
              >
                <option>Beginner</option>
                <option>Intermediate</option>
                <option>Advanced</option>
                <option>Pro</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">Location</label>
              <input
                type="text"
                name="location"
                value={draft.location || ''}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                data-testid="profile-location-input"
              />
            </div>

              <div className="col-span-2">
                <label className="block text-sm font-semibold text-gray-700 mb-1">Favorite Course</label>
                <input
                  type="text"
                  name="favoriteCourse"
                  value={draft.favoriteCourse || ''}
                  onChange={handleChange}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                  data-testid="profile-favorite-course-input"
                />
                <label className="mt-1 inline-flex items-center gap-2 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.privacy?.favoriteCourse)}
                    onChange={(e) =>
                      setDraft((p) => ({
                        ...p,
                        privacy: { ...(p.privacy || {}), favoriteCourse: e.target.checked },
                      }))
                    }
                    data-testid="profile-favorite-course-private"
                  />
                  Keep private (hide from other players)
                </label>
              </div>

              <div className="col-span-2">
                <label className="block text-sm font-semibold text-gray-700 mb-1">Home Course</label>
                <input
                  type="text"
                  name="homeCourse"
                  value={draft.homeCourse || ''}
                  onChange={handleChange}
                  placeholder="The course you play most often"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                  data-testid="profile-home-course-input"
                />
                <label className="mt-1 inline-flex items-center gap-2 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.privacy?.homeCourse)}
                    onChange={(e) =>
                      setDraft((p) => ({
                        ...p,
                        privacy: { ...(p.privacy || {}), homeCourse: e.target.checked },
                      }))
                    }
                    data-testid="profile-home-course-private"
                  />
                  Keep private (hide from other players)
                </label>
              </div>

              <div className="col-span-2">
                <label className="block text-sm font-semibold text-gray-700 mb-1">Favorite Frisbee</label>
                <input
                  type="text"
                  name="favoriteFrisbee"
                  value={draft.favoriteFrisbee || ''}
                  onChange={handleChange}
                  placeholder="e.g. Innova Destroyer, Discraft Buzzz"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                  data-testid="profile-favorite-frisbee-input"
                />
                <label className="mt-1 inline-flex items-center gap-2 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.privacy?.favoriteFrisbee)}
                    onChange={(e) =>
                      setDraft((p) => ({
                        ...p,
                        privacy: { ...(p.privacy || {}), favoriteFrisbee: e.target.checked },
                      }))
                    }
                    data-testid="profile-favorite-frisbee-private"
                  />
                  Keep private (hide from other players)
                </label>
              </div>

            <div className="col-span-2">
              <label className="block text-sm font-semibold text-gray-700 mb-1">Bio</label>
              <textarea
                name="bio"
                value={draft.bio || ''}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green h-24"
                data-testid="profile-bio-input"
              />
            </div>
          </div>

          <button
            onClick={handleSave}
            disabled={loading}
            className="mt-6 w-full bg-disc-gold hover:bg-disc-gold/90 text-white font-bold py-3 rounded-lg transition disabled:opacity-50"
            data-testid="profile-save-btn"
          >
            {loading ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      ) : (
        <>
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            How others see you
          </h3>
          <PublicProfilePreview
            player={{
              uid: profile.uid,
              name: profile.name || 'You',
              age: profile.age,
              skillLevel: profile.skillLevel,
              location: profile.location,
              favoriteCourse: profile.favoriteCourse,
              favoriteFrisbee: profile.favoriteFrisbee,
              homeCourse: profile.homeCourse,
              bio: profile.bio,
              interests: profile.interests?.length ? profile.interests : DEFAULT_INTERESTS,
              profilePictureUrl: profile.profilePictureUrl,
              bannerUrl: profile.bannerUrl,
            }}
          />
        </>
      )}
    </div>
  );
}
