import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { api } from '../lib/api';
import PublicProfilePreview from '../components/PublicProfilePreview';

const DEFAULT_INTERESTS = ['tournaments', 'hiking', 'casual play'];

export default function Profile() {
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  useEffect(() => {
    if (profile) setDraft(profile);
  }, [profile]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setDraft((prev) => ({ ...prev, [name]: value }));
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
        bio: draft.bio,
        interests: draft.interests,
        profilePictureUrl: draft.profilePictureUrl,
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

  if (isEditing) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8" data-testid="profile-edit-view">
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          <div className="bg-gradient-to-r from-disc-green to-disc-purple h-32" />
          <div className="px-6 pb-6">
            <div className="flex justify-between items-start mb-6">
              <div className="flex gap-4 items-end">
                <img
                  src={
                    draft.profilePictureUrl ||
                    'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&h=150&fit=crop'
                  }
                  alt="Profile"
                  className="w-32 h-32 rounded-full border-4 border-white -mt-16 shadow-lg object-cover"
                />
                <div>
                  <h1 className="text-3xl font-bold text-gray-800">
                    {draft.name || 'Your name'}
                    {draft.age ? `, ${draft.age}` : ''}
                  </h1>
                  <p className="text-disc-gold text-lg font-semibold">
                    {draft.skillLevel || 'Beginner'}
                  </p>
                </div>
              </div>

              <button
                onClick={() => {
                  setDraft(profile);
                  setIsEditing(false);
                }}
                className="bg-gray-200 hover:bg-gray-300 text-gray-800 font-bold py-2 px-6 rounded-lg transition"
                data-testid="profile-cancel-btn"
              >
                Cancel
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
        </div>
      </div>
    );
  }

  const previewPlayer = {
    uid: profile.uid,
    name: profile.name || 'You',
    age: profile.age,
    skillLevel: profile.skillLevel,
    location: profile.location,
    favoriteCourse: profile.favoriteCourse,
    favoriteFrisbee: profile.favoriteFrisbee,
    bio: profile.bio,
    interests: profile.interests?.length ? profile.interests : DEFAULT_INTERESTS,
    image:
      profile.profilePictureUrl ||
      'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop',
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8" data-testid="profile-view">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-disc-green">Profile preview</h1>
          <p className="text-sm text-gray-600">This is exactly what other players see.</p>
        </div>
        <button
          onClick={() => setIsEditing(true)}
          className="bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 px-6 rounded-lg transition"
          data-testid="profile-edit-btn"
        >
          Edit Profile
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

      <PublicProfilePreview player={previewPlayer} />
    </div>
  );
}
