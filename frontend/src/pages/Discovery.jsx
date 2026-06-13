import { useEffect } from 'react';
import { useMatchStore } from '../store/matchStore';
import PlayerCard from '../components/PlayerCard';

export default function Discovery() {
  const { deck, loading, fetchDeck, likePlayer, passPlayer } = useMatchStore();

  useEffect(() => {
    fetchDeck();
  }, [fetchDeck]);

  const currentPlayer = deck[0];

  const handleLike = async (player) => {
    await likePlayer(player);
  };

  const handlePass = async (player) => {
    await passPlayer(player);
  };

  if (loading && deck.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-loading">
        <p className="text-center text-gray-500">Loading players…</p>
      </div>
    );
  }

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

  // Map server profile -> PlayerCard expected shape (image instead of profilePictureUrl).
  const cardPlayer = {
    ...currentPlayer,
    id: currentPlayer.uid,
    image: currentPlayer.profilePictureUrl,
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-12" data-testid="discovery-view">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-disc-green mb-2">Find Your Ace Match</h1>
        <p className="text-gray-600">{deck.length} players to discover</p>
      </div>

      <div className="flex justify-center">
        <PlayerCard
          player={cardPlayer}
          onLike={() => handleLike(currentPlayer)}
          onPass={() => handlePass(currentPlayer)}
        />
      </div>
    </div>
  );
}
