/**
 * PublicProfilePreview
 *
 * Renders a profile in the same layout used by the discovery PlayerCard, so the
 * "preview" on the Profile page mirrors what other players see publicly.
 * Action buttons are intentionally omitted - this is read-only.
 */
export default function PublicProfilePreview({ player }) {
  if (!player) return null;

  return (
    <div
      className="bg-white rounded-2xl shadow-lg overflow-hidden max-w-sm mx-auto"
      data-testid="public-profile-preview"
    >
      {/* Player Image */}
      <div className="relative h-96 bg-gray-300">
        <img
          src={player.image || 'https://via.placeholder.com/400x400'}
          alt={player.name}
          className="w-full h-full object-cover"
        />
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black via-transparent to-transparent p-6">
          <h2 className="text-3xl font-bold text-white">
            {player.name}, {player.age}
          </h2>
          <p className="text-disc-gold text-lg">{player.skillLevel}</p>
        </div>
      </div>

      {/* Player Info */}
      <div className="p-6">
        <div className="mb-4 space-y-2">
          {player.location && (
            <p className="text-gray-600">
              <span className="font-semibold text-gray-800">Location:</span> {player.location}
            </p>
          )}
          {player.favoriteCourse && (
            <p className="text-gray-600">
              <span className="font-semibold text-gray-800">Favorite Course:</span>{' '}
              {player.favoriteCourse}
            </p>
          )}
          {player.favoriteFrisbee && (
            <p className="text-gray-600" data-testid="public-profile-favorite-frisbee">
              <span className="font-semibold text-gray-800">Favorite Frisbee:</span>{' '}
              {player.favoriteFrisbee}
            </p>
          )}
          {player.bio && (
            <p className="text-gray-600">
              <span className="font-semibold text-gray-800">Bio:</span> {player.bio}
            </p>
          )}
        </div>

        {player.interests && player.interests.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {player.interests.map((interest) => (
              <span
                key={interest}
                className="bg-disc-green text-white px-3 py-1 rounded-full text-sm"
              >
                {interest}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
