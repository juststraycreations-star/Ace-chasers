import { useState, useEffect } from 'react';
import { useMatchStore } from '../store/matchStore';
import PlayerCard from '../components/PlayerCard';

// Mock data - replace with API calls
const MOCK_PLAYERS = [
  {
    id: 1,
    name: 'Sarah',
    age: 28,
    skillLevel: 'Intermediate',
    location: 'Portland, OR',
    favoriteCourse: 'Milo McIver',
    bio: 'Love weekend rounds and exploring new courses!',
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=400&fit=crop',
    interests: ['hiking', 'coffee', 'tournaments'],
  },
  {
    id: 2,
    name: 'Jessica',
    age: 26,
    skillLevel: 'Beginner',
    location: 'Seattle, WA',
    favoriteCourse: 'Rattlesnake Ledge',
    bio: 'Just getting into disc golf, looking for friendly players!',
    image: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop',
    interests: ['outdoors', 'casual play', 'nature'],
  },
  {
    id: 3,
    name: 'Amanda',
    age: 30,
    skillLevel: 'Advanced',
    location: 'Eugene, OR',
    favoriteCourse: 'Willamette Park',
    bio: 'Competitive player looking for serious rounds',
    image: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop',
    interests: ['competitions', 'fitness', 'travel'],
  },
];

export default function Discovery() {
  const { players, currentPlayerIndex, likePlayer, passPlayer } = useMatchStore();
  const [localPlayers, setLocalPlayers] = useState(MOCK_PLAYERS);

  useEffect(() => {
    // Initialize with mock data - replace with API call
    setLocalPlayers(MOCK_PLAYERS);
  }, []);

  const currentPlayer = localPlayers[currentPlayerIndex];

  const handleLike = (playerId) => {
    likePlayer(playerId);
    setLocalPlayers(prev => [
      ...prev.slice(currentPlayerIndex + 1),
    ]);
  };

  const handlePass = (playerId) => {
    passPlayer(playerId);
    setLocalPlayers(prev => [
      ...prev.slice(currentPlayerIndex + 1),
    ]);
  };

  if (!currentPlayer) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-4">
            No more players to discover! 🎉
          </h2>
          <p className="text-gray-600 mb-6">
            Check your messages to see who liked you back.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-12">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-disc-green mb-2">Find Your Ace Match</h1>
        <p className="text-gray-600">
          {localPlayers.length - currentPlayerIndex} players to discover
        </p>
      </div>

      <div className="flex justify-center">
        <PlayerCard
          player={currentPlayer}
          onLike={handleLike}
          onPass={handlePass}
        />
      </div>
    </div>
  );
}
