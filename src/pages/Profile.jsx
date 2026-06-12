import { useState } from 'react';
import { useAuthStore } from '../store/authStore';

export default function Profile() {
  const user = useAuthStore((state) => state.user);
  const [isEditing, setIsEditing] = useState(false);
  const [profile, setProfile] = useState(
    user || {
      name: 'Alex',
      age: 29,
      skillLevel: 'Intermediate',
      location: 'Portland, OR',
      favoriteCourse: 'Milo McIver',
      bio: 'Love disc golf and meeting new players!',
      interests: ['tournaments', 'hiking', 'casual play'],
    }
  );

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSave = () => {
    setIsEditing(false);
    // TODO: Call API to save profile
  };

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
                src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&h=150&fit=crop"
                alt="Profile"
                className="w-32 h-32 rounded-full border-4 border-white -mt-16 shadow-lg"
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
                  className="w-full bg-disc-gold hover:bg-disc-gold/90 text-white font-bold py-3 rounded-lg transition"
                >
                  Save Changes
                </button>
              </>
            ) : (
              <>
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-semibold text-gray-800">Location:</span> {profile.location}
                  </p>
                  <p className="text-sm text-gray-600">
                    <span className="font-semibold text-gray-800">Favorite Course:</span> {profile.favoriteCourse}
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-800 mb-2">Bio</h3>
                  <p className="text-gray-600">{profile.bio}</p>
                </div>

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
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
