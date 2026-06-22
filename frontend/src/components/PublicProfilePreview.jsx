import { resolveImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';

/**
 * PublicProfilePreview
 *
 * Read-only view of a profile in the same shape other players see. The banner
 * spans the top, the circular thumbnail overlaps it, and the public profile
 * fields render below.
 *
 * Optional `actions` slot renders at the very bottom (e.g. Nice / Message /
 * Player buttons on the Discovery grid).
 */
export default function PublicProfilePreview({ player, actions, compact = false }) {
  if (!player) return null;

  const banner = resolveImageUrl(player.bannerUrl);
  const avatar =
    resolveImageUrl(player.profilePictureUrl) || player.image || DEFAULT_AVATAR;

  const bannerH = compact ? 'h-24' : 'h-32';
  const avatarSize = compact ? 'w-20 h-20' : 'w-24 h-24';
  const overlap = compact ? '-mt-10' : '-mt-12';
  const nameSize = compact ? 'text-xl' : 'text-2xl';

  return (
    <div
      className="bg-white rounded-2xl shadow-lg overflow-hidden max-w-sm w-full mx-auto"
      data-testid="public-profile-preview"
    >
      {/* Banner */}
      <div
        className={`${bannerH} bg-gradient-to-r from-disc-green to-disc-purple bg-cover bg-center`}
        style={banner ? { backgroundImage: `url(${banner})` } : undefined}
        data-testid="public-profile-banner"
      />

      {/* Avatar + identity */}
      <div className={`px-6 pb-6 ${overlap}`}>
        <img
          src={avatar}
          alt={player.name || 'Profile'}
          className={`${avatarSize} rounded-full border-4 border-white shadow-lg object-cover bg-gray-200`}
          data-testid="public-profile-thumbnail"
        />
        <div className="mt-2">
          {(player.name || player.age) && (
            <h2 className={`${nameSize} font-bold text-gray-800`}>
              {player.name}
              {player.age ? `, ${player.age}` : ''}
            </h2>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-0.5">
            {player.skillLevel && (
              <p className="text-disc-gold font-semibold">{player.skillLevel}</p>
            )}
            {player.aceClub && (
              <span
                className="bg-disc-gold/15 text-disc-gold border border-disc-gold/40 text-xs font-bold px-2 py-0.5 rounded-full"
                data-testid="public-profile-ace-club"
                title={
                  player.aceClubCount != null
                    ? `Ace Club member · ${player.aceClubCount} aces`
                    : 'Ace Club member'
                }
              >
                🏆 Ace Club
                {player.aceClubCount != null ? ` (${player.aceClubCount})` : ''}
              </span>
            )}
          </div>
        </div>

        {/* Info */}
        <div className="mt-4 space-y-2">
          {player.location && (
            <p className="text-gray-600 text-sm">
              <span className="font-semibold text-gray-800">Location:</span>{' '}
              {player.location}
              {typeof player.distance_miles === 'number' && (
                <span
                  className="ml-1 text-disc-green font-semibold"
                  data-testid={`public-profile-distance-${player.uid}`}
                >
                  · {player.distance_miles} mi away
                </span>
              )}
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
              <span className="font-semibold text-gray-800">Home Course:</span>{' '}
              {player.homeCourse}
            </p>
          )}
          {player.favoriteFrisbee && (
            <p className="text-gray-600 text-sm" data-testid="public-profile-favorite-frisbee">
              <span className="font-semibold text-gray-800">Favorite Frisbee:</span>{' '}
              {player.favoriteFrisbee}
            </p>
          )}
          {player.interestedIn && (
            <p className="text-gray-600 text-sm" data-testid="public-profile-interested-in">
              <span className="font-semibold text-gray-800">Interested in:</span>{' '}
              {player.interestedIn}
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

        {actions && (
          <div className="mt-4 pt-4 border-t border-gray-100">{actions}</div>
        )}
      </div>
    </div>
  );
}
