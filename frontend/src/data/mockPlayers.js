/**
 * Centralized mock player data used by both the Discovery deck and the Likes
 * page. Replace with API calls when wiring up a real backend.
 */
export const MOCK_PLAYERS = [
  {
    id: 1,
    name: 'Sarah',
    age: 28,
    skillLevel: 'Intermediate',
    location: 'Portland, OR',
    favoriteCourse: 'Milo McIver',
    favoriteFrisbee: 'Innova Leopard',
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
    favoriteFrisbee: 'Discraft Buzzz',
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
    favoriteFrisbee: 'Innova Destroyer',
    bio: 'Competitive player looking for serious rounds',
    image: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop',
    interests: ['competitions', 'fitness', 'travel'],
  },
];

export default MOCK_PLAYERS;
