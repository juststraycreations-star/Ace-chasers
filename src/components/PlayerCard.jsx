export default function PlayerCard({ player, onLike, onPass }) {
  if (!player) return null;

  return (
    <div className="bg-white rounded-2xl shadow-lg overflow-hidden max-w-sm mx-auto">
      {/* Player Image */}
      <div className="relative h-96 bg-gray-300">
        <img
          src={player.image || 'https://via.placeholder.com/400x400'}
          alt={player.name}
          className="w-full h-full object-cover"
        />
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black via-transparent to-transparent p-6">
          <h2 className="text-3xl font-bold text-white">{player.name}, {player.age}</h2>
          <p className="text-disc-gold text-lg">{player.skillLevel}</p>
        </div>
      </div>

      {/* Player Info */}
      <div className="p-6">
        <div className="mb-4">
          <p className="text-gray-600 mb-2">
            <span className="font-semibold text-gray-800">Location:</span> {player.location}
          </p>
          <p className="text-gray-600 mb-2">
            <span className="font-semibold text-gray-800">Favorite Course:</span> {player.favoriteCourse}
          </p>
          <p className="text-gray-600">
            <span className="font-semibold text-gray-800">Bio:</span> {player.bio}
          </p>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-2 mb-6">
          {player.interests?.map((interest) => (
            <span
              key={interest}
              className="bg-disc-green text-white px-3 py-1 rounded-full text-sm"
            >
              {interest}
            </span>
          ))}
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4 justify-center">
          <button
            onClick={() => onPass(player.id)}
            className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-3 px-8 rounded-lg transition w-1/3"
          >
            ✕
          </button>
          <button
            onClick={() => onLike(player.id)}
            className="bg-disc-gold hover:bg-disc-gold/90 text-white font-bold py-3 px-8 rounded-lg transition w-1/3"
          >
            ❤️
          </button>
        </div>
      </div>
    </div>
  );
}
