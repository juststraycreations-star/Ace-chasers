import { resolveImageUrl } from '../lib/images';

const DEFAULT_AVATAR =
  'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop';

/**
 * PublicProfilePreview
 *
 * Read-only view of a profile in the same shape other players see. The banner
 * spans the top, the circular thumbnail overlaps it, and the public profile
 * fields render below.
 */
export default function PublicProfilePreview({ player }) {
  if (!player) return null;

  const banner = resolveImageUrl(player.bannerUrl);
  const avatar = resolveImageUrl(player.profilePictureUrl) || player.image || DEFAULT_AVATAR;

  return (
    <div
      className="bg-white rounded-2xl shadow-lg overflow-hidden max-w-sm mx-auto"
      data-testid="public-profile-preview"
    >
      {/* Banner */}
      <div
        className="h-32 bg-gradient-to-r from-disc-green to-disc-purple bg-cover bg-center"
        style={banner ? { backgroundImage: `url(${banner})` } : undefined}
        data-testid="public-profile-banner"
      />

      {/* Avatar + identity */}
      <div className="px-6 pb-6 -mt-12">
        <img
          src={avatar}
          alt={player.name || 'Profile'}
          className="w-24 h-24 rounded-full border-4 border-white shadow-lg object-cover bg-gray-200"
          data-testid="public-profile-thumbnail"
        />
        <div className="mt-2">
          <h2 className="text-2xl font-bold text-gray-800">
            {player.name}
            {player.age ? `, ${player.age}` : ''}
          </h2>
          {player.skillLevel && (
            <p className="text-disc-gold font-semibold">{player.skillLevel}</p>
          )}
        </div>

        {/* Info */}
        <div className="mt-4 space-y-2">
          {player.location && (
            <p className="text-gray-600 text-sm">
              <span className="font-semibold text-gray-800">Location:</span> {player.location}
            </p>
          )}
          {player.favoriteCourse && (
            <p className="text-gray-600 text-sm">
              <span className="font-semibold text-gray-800">Favorite Course:</span>{' '}
              {player.favoriteCourse}
            </p>
          )}
          {player.homeCourse && (
            <p className="text-gray-600 text-sm" data-testid="public-profile-home-course">
              <span className="font-semibold text-gray-800">Home Course:</span> {player.homeCourse}
            </p>
          )}
          {player.favoriteFrisbee && (
            <p className="text-gray-600 text-sm" data-testid="public-profile-favorite-frisbee">
              <span className="font-semibold text-gray-800">Favorite Frisbee:</span>{' '}
              {player.favoriteFrisbee}
            </p>
          )}
          {player.bio && (
            <p className="text-gray-600 text-sm">
              <span className="font-semibold text-gray-800">Bio:</span> {player.bio}
            </p>
          )}
        </div>

        {player.interests && player.interests.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
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
