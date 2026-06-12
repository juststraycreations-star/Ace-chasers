import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useProfileStore } from '../store/profileStore';

export default function Profile() {
  const user = useAuthStore((state) => state.user);
  const updateUser = useAuthStore((state) => state.updateUser);
  const { currentProfile, saveProfile, updateProfileField, fetchProfile } = useProfileStore();
  
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
    bio: 'Love disc golf and meeting new players!',
    interests: ['tournaments', 'hiking', 'casual play'],
    profilePictureUrl: '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSave = async () => {
    if (!user?.id) return;

    setLoading(true);
    setSaveMessage('');

    try {
      // Save to store (automatically persists)
      await saveProfile(user.id, profile);

      // Update auth user data
      updateUser({
        name: profile.name,
        age: profile.age,
        skillLevel: profile.skillLevel,
      });

      setSaveMessage('Profile saved successfully! ✓');
      setIsEditing(false);

      // Clear message after 3 seconds
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
        <div className="text-center">Loading profile...</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-disc-green to-disc-purple h-32"></div>

        {/* Profile Content */}
        <div className="px-6 pb-6">
          {/* Profile Picture */}
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
              onClick={() => setIsEditing(!isEditing)}
              className="bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 px-6 rounded-lg transition"
            >
              {isEditing ? 'Cancel' : 'Edit Profile'}
            </button>
          </div>

          {/* Success/Error Message */}
          {saveMessage && (
            <div className={`mb-4 px-4 py-3 rounded ${
              saveMessage.includes('successfully') 
                ? 'bg-green-100 text-green-700 border border-green-400' 
                : 'bg-yellow-100 text-yellow-700 border border-yellow-400'
            }`}>
              {saveMessage}
            </div>
          )}

          {/* Profile Information */}
          <div className="space-y-4">
            {isEditing ? (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">
                      Name
                    </label>
                    <input
                      type="text"
                      name="name"
                      value={profile.name}
                      onChange={handleChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">
                      Age
                    </label>
                    <input
                      type="number"
                      name="age"
                      value={profile.age}
                      onChange={handleChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">
                      Skill Level
                    </label>
                    <select
                      name="skillLevel"
                      value={profile.skillLevel}
                      onChange={handleChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                    >
                      <option>Beginner</option>
                      <option>Intermediate</option>
                      <option>Advanced</option>
                      <option>Pro</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1">
                      Location
                    </label>
                    <input
                      type="text"
                      name="location"
                      value={profile.location}
                      onChange={handleChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                    />
                  </div>

                  <div className="col-span-2">
                    <label className="block text-sm font-semibold text-gray-700 mb-1">
                      Favorite Course
                    </label>
                    <input
                      type="text"
                      name="favoriteCourse"
                      value={profile.favoriteCourse}
                      onChange={handleChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                    />
                  </div>

                  <div className="col-span-2">
                    <label className="block text-sm font-semibold text-gray-700 mb-1">
                      Bio
                    </label>
                    <textarea
                      name="bio"
                      value={profile.bio}
                      onChange={handleChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green h-24"
                    />
                  </div>
                </div>

                <button
                  onClick={handleSave}
                  disabled={loading}
                  className="w-full bg-disc-gold hover:bg-disc-gold/90 text-white font-bold py-3 rounded-lg transition disabled:opacity-50"
                >
                  {loading ? 'Saving...' : 'Save Changes'}
                </button>
              </>
            ) : (
              <>
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-semibold text-gray-800">Location:</span> {profile.location || 'Not specified'}
                  </p>
                  <p className="text-sm text-gray-600">
                    <span className="font-semibold text-gray-800">Favorite Course:</span> {profile.favoriteCourse || 'Not specified'}
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-800 mb-2">Bio</h3>
                  <p className="text-gray-600">{profile.bio}</p>
                </div>

                {profile.interests && profile.interests.length > 0 && (
                  <div>
                    <h3 className="text-lg font-semibold text-gray-800 mb-2">Interests</h3>
                    <div className="flex flex-wrap gap-2">
                      {profile.interests.map(interest => (
                        <span
                          key={interest}
                          className="bg-disc-green text-white px-4 py-2 rounded-full text-sm"
                        >
                          {interest}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="pt-4 border-t text-xs text-gray-500">
                  Profile saved locally and will persist when you log back in.
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
