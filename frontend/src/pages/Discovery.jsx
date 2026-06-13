import { useMatchStore } from '../store/matchStore';
import PlayerCard from '../components/PlayerCard';
import { MOCK_PLAYERS } from '../data/mockPlayers';

export default function Discovery() {
  const { currentPlayerIndex, likedPlayers, passedPlayers, likePlayer, passPlayer } =
    useMatchStore();

  // Filter out players the user has already swiped on, then pick the current one.
  const deck = MOCK_PLAYERS.filter(
    (p) => !likedPlayers[p.id] && !passedPlayers[p.id]
  );
  const currentPlayer = deck[0];

  const handleLike = (player) => {
    likePlayer(player);
  };

  const handlePass = (player) => {
    passPlayer(player);
  };

  if (!currentPlayer) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-empty">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-4">
            No more players to discover! 🎉
          </h2>
          <p className="text-gray-600 mb-6">
            Check your <span className="font-semibold">Likes</span> tab to see who you matched with.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-view">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-disc-green mb-2">Find Your Ace Match</h1>
        <p className="text-gray-600">{deck.length} players to discover</p>
      </div>

      <div className="flex justify-center">
        <PlayerCard player={currentPlayer} onLike={handleLike} onPass={handlePass} />
      </div>
    </div>
  );
}
