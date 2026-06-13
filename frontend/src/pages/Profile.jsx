import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useProfileStore } from '../store/profileStore';
import PublicProfilePreview from '../components/PublicProfilePreview';

const DEFAULT_INTERESTS = ['tournaments', 'hiking', 'casual play'];

export default function Profile() {
  const user = useAuthStore((state) => state.user);
  const updateUser = useAuthStore((state) => state.updateUser);
  const { currentProfile, saveProfile, fetchProfile } = useProfileStore();

  const [isEditing, setIsEditing] = useState(false);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  // Load profile on component mount
  useEffect(() => {
    if (user?.id) {
      fetchProfile(user.id).then((data) => {
        setProfile(data || createDefaultProfile());
      });
    }
  }, [user?.id, fetchProfile]);

  // Update local profile when store updates
  useEffect(() => {
    if (currentProfile) {
      setProfile(currentProfile);
    }
  }, [currentProfile]);

  const createDefaultProfile = () => ({
    name: user?.name || 'Alex',
    age: user?.age || 29,
    skillLevel: user?.skillLevel || 'Intermediate',
    location: '',
    favoriteCourse: '',
    favoriteFrisbee: '',
    bio: 'Love disc golf and meeting new players!',
    interests: DEFAULT_INTERESTS,
    profilePictureUrl: '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSave = async () => {
    if (!user?.id) return;

    setLoading(true);
    setSaveMessage('');

    try {
      await saveProfile(user.id, profile);

      updateUser({
        name: profile.name,
        age: profile.age,
        skillLevel: profile.skillLevel,
      });

      setSaveMessage('Profile saved successfully! ✓');
      setIsEditing(false);
      setTimeout(() => setSaveMessage(''), 3000);
    } catch (error) {
      setSaveMessage('Failed to save profile. Changes saved locally.');
      console.error('Save error:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!profile) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="text-center" data-testid="profile-loading">Loading profile...</div>
      </div>
    );
  }

  // ----- EDIT MODE -----
  if (isEditing) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8" data-testid="profile-edit-view">
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          <div className="bg-gradient-to-r from-disc-green to-disc-purple h-32"></div>
          <div className="px-6 pb-6">
            <div className="flex justify-between items-start mb-6">
              <div className="flex gap-4 items-end">
                <img
                  src={profile.profilePictureUrl || 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&h=150&fit=crop'}
                  alt="Profile"
                  className="w-32 h-32 rounded-full border-4 border-white -mt-16 shadow-lg object-cover"
                />
                <div>
                  <h1 className="text-3xl font-bold text-gray-800">
                    {profile.name}, {profile.age}
                  </h1>
                  <p className="text-disc-gold text-lg font-semibold">{profile.skillLevel}</p>
                </div>
              </div>

              <button
                onClick={() => setIsEditing(false)}
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
                  value={profile.name}
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
                  value={profile.age}
                  onChange={handleChange}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                  data-testid="profile-age-input"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">Skill Level</label>
                <select
                  name="skillLevel"
                  value={profile.skillLevel}
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
                  value={profile.location}
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
                  value={profile.favoriteCourse}
                  onChange={handleChange}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                  data-testid="profile-favorite-course-input"
                />
              </div>

              <div className="col-span-2">
                <label className="block text-sm font-semibold text-gray-700 mb-1">
                  Favorite Frisbee
                </label>
                <input
                  type="text"
                  name="favoriteFrisbee"
                  value={profile.favoriteFrisbee || ''}
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
                  value={profile.bio}
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
              {loading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ----- VIEW MODE: matches the public-profile (PlayerCard) layout -----
  const previewPlayer = {
    id: user?.id || 'me',
    name: profile.name,
    age: profile.age,
    skillLevel: profile.skillLevel,
    location: profile.location,
    favoriteCourse: profile.favoriteCourse,
    favoriteFrisbee: profile.favoriteFrisbee,
    bio: profile.bio,
    interests: profile.interests,
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
