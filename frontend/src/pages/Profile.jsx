import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useMatchStore } from '../store/matchStore';
import { api } from '../lib/api';
import { compressImage } from '../lib/compressImage';
import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import {
  INTEREST_TAG_OPTIONS,
  activeInterestTags,
  toggleInterestTag,
} from '../lib/interestTags';
import PublicProfilePreview from '../components/PublicProfilePreview';

const DEFAULT_INTERESTS = ['tournaments', 'hiking', 'casual play'];
const MAX_RAW_BYTES = 30 * 1024 * 1024;

export default function Profile() {
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);
  const friends = useMatchStore((s) => s.friends);
  const inbox = useMatchStore((s) => s.inbox);
  const fetchFriends = useMatchStore((s) => s.fetchFriends);
  const fetchInbox = useMatchStore((s) => s.fetchInbox);

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

  useEffect(() => {
    fetchFriends();
    fetchInbox();
  }, [fetchFriends, fetchInbox]);

  const pendingRequestsCount = inbox?.incoming_friend_requests?.length || 0;

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
      const res = await api.post(endpoint, form);
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
        interestedIn: draft.interestedIn,
        aceClub: !!draft.aceClub,
        aceClubCount: draft.aceClub && draft.aceClubCount ? Number(draft.aceClubCount) : null,
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

      {pendingRequestsCount > 0 && (
        <div
          className="mb-4 bg-disc-gold/15 border border-disc-gold/40 rounded-lg px-4 py-3 flex items-center justify-between"
          data-testid="profile-pending-requests-notice"
        >
          <div className="text-sm text-disc-green font-semibold">
            🤝 You have <span className="font-bold">{pendingRequestsCount}</span> pending friend request
            {pendingRequestsCount === 1 ? '' : 's'}.
          </div>
          <Link
            to="/likes"
            className="text-xs uppercase tracking-wide font-bold text-disc-green hover:text-disc-green/80"
            data-testid="profile-view-requests-link"
          >
            View →
          </Link>
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

          {isEditing && !profile.profilePictureUrl && (
            <div
              className="mt-3 bg-disc-gold/15 border border-disc-gold/40 rounded-lg px-3 py-2 text-sm text-gray-800 flex items-start gap-2"
              data-testid="profile-avatar-prompt"
            >
              <span aria-hidden="true">📸</span>
              <p className="flex-1">
                <strong className="font-semibold">Add a profile picture!</strong> Players are
                4× more likely to make friends when your profile has a photo. Tap the green 📷
                button on your avatar above.
              </p>
            </div>
          )}

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
                placeholder="e.g. Seattle, WA"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                data-testid="profile-location-input"
              />
              <label className="mt-1 inline-flex items-center gap-2 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={Boolean(draft.privacy?.location)}
                  onChange={(e) =>
                    setDraft((p) => ({
                      ...p,
                      privacy: { ...(p.privacy || {}), location: e.target.checked },
                    }))
                  }
                  data-testid="profile-location-private-toggle"
                />
                <span>Keep my location private (won&apos;t appear on Discovery)</span>
              </label>
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
              <label className="block text-sm font-semibold text-gray-700 mb-1">Interested in</label>
              <div
                className="flex flex-wrap gap-2 mb-2"
                data-testid="profile-interested-in-tags"
              >
                {INTEREST_TAG_OPTIONS.map((opt) => {
                  const active = activeInterestTags(draft.interestedIn).has(opt.value);
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() =>
                        setDraft((p) => ({
                          ...p,
                          interestedIn: toggleInterestTag(p.interestedIn, opt),
                        }))
                      }
                      className={
                        active
                          ? 'bg-disc-gold text-white font-bold text-sm px-3 py-1.5 rounded-full shadow'
                          : 'border border-disc-gold text-disc-gold hover:bg-disc-gold/10 font-semibold text-sm px-3 py-1.5 rounded-full'
                      }
                      data-testid={`profile-interested-in-tag-${opt.value}`}
                      aria-pressed={active}
                    >
                      {active ? '✓ ' : '+ '}
                      {opt.label}
                    </button>
                  );
                })}
              </div>
              <input
                type="text"
                name="interestedIn"
                value={draft.interestedIn || ''}
                onChange={handleChange}
                placeholder="Tap a chip above, or write your own (e.g. early-morning rounds)"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                data-testid="profile-interested-in-input"
                maxLength={200}
              />
              <p className="text-xs text-gray-500 mt-1">
                Pick what you&apos;re looking for so the Discovery filter can match you with players who want the same thing.
              </p>
              <label className="mt-1 inline-flex items-center gap-2 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={Boolean(draft.privacy?.interestedIn)}
                  onChange={(e) =>
                    setDraft((p) => ({
                      ...p,
                      privacy: { ...(p.privacy || {}), interestedIn: e.target.checked },
                    }))
                  }
                  data-testid="profile-interested-in-private"
                />
                Keep private (hide from other players)
              </label>
            </div>

            <div className="col-span-2 border-t border-gray-100 pt-4">
              <label className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                <input
                  type="checkbox"
                  checked={Boolean(draft.aceClub)}
                  onChange={(e) =>
                    setDraft((p) => ({
                      ...p,
                      aceClub: e.target.checked,
                      // Clear count when toggled off.
                      aceClubCount: e.target.checked ? p.aceClubCount : null,
                    }))
                  }
                  data-testid="profile-ace-club-toggle"
                />
                🏆 I&apos;m in an Ace Club
              </label>
              {draft.aceClub && (
                <div className="mt-2">
                  <label
                    htmlFor="profile-ace-club-count"
                    className="block text-xs font-semibold text-gray-700 mb-1"
                  >
                    How many aces?
                  </label>
                  <input
                    id="profile-ace-club-count"
                    type="number"
                    min="0"
                    max="10000"
                    value={draft.aceClubCount ?? ''}
                    onChange={(e) =>
                      setDraft((p) => ({
                        ...p,
                        aceClubCount: e.target.value === '' ? null : Number(e.target.value),
                      }))
                    }
                    placeholder="0"
                    className="w-32 border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                    data-testid="profile-ace-club-count-input"
                  />
                </div>
              )}
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
              interestedIn: profile.interestedIn,
              aceClub: profile.aceClub,
              aceClubCount: profile.aceClubCount,
              bio: profile.bio,
              interests: profile.interests?.length ? profile.interests : DEFAULT_INTERESTS,
              profilePictureUrl: profile.profilePictureUrl,
              bannerUrl: profile.bannerUrl,
            }}
          />
        </>
      )}

      <section
        className="mt-8 bg-white rounded-2xl shadow-lg p-6"
        data-testid="profile-friends-section"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-disc-green">
            🥏 Your Friends
            <span className="ml-2 text-sm text-gray-500 font-normal">
              ({friends?.length || 0})
            </span>
          </h2>
          {(friends?.length || 0) > 0 && (
            <Link
              to="/likes"
              className="text-xs uppercase tracking-wide font-bold text-disc-green hover:text-disc-green/80"
              data-testid="profile-see-all-friends"
            >
              See all →
            </Link>
          )}
        </div>
        {(friends?.length || 0) === 0 ? (
          <p className="text-sm text-gray-500">
            No friends yet. Head to{' '}
            <Link to="/discovery" className="text-disc-green font-semibold hover:underline">
              Discovery
            </Link>{' '}
            and tap 🤝 Friend on someone to send a request.
          </p>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {friends.slice(0, 12).map((f) => (
              <Link
                key={f.uid}
                to={`/players/${f.uid}`}
                className="flex flex-col items-center group"
                data-testid={`profile-friend-${f.uid}`}
              >
                <img
                  src={resolveImageUrl(f.profilePictureUrl) || DEFAULT_AVATAR}
                  alt={f.name || 'Friend'}
                  className="w-14 h-14 rounded-full object-cover mb-1 group-hover:ring-2 group-hover:ring-disc-green transition"
                />
                <span className="text-xs font-semibold text-gray-700 text-center truncate w-full">
                  {f.name || 'Player'}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
