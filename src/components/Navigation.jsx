import { Link, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export default function Navigation() {
  const location = useLocation();
  const logout = useAuthStore((state) => state.logout);

  const isActive = (path) => location.pathname === path;

  const handleLogout = () => {
    logout();
  };

  return (
    <nav className="bg-disc-green text-white shadow-lg sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center">
        <Link to="/discovery" className="text-2xl font-bold">
          ⛳ Ace Chasers
        </Link>

        <div className="flex gap-6 items-center">
          <Link
            to="/discovery"
            className={`font-semibold transition ${
              isActive('/discovery')
                ? 'text-disc-gold'
                : 'hover:text-disc-gold'
            }`}
          >
            Discovery
          </Link>
          <Link
            to="/messages"
            className={`font-semibold transition ${
              isActive('/messages')
                ? 'text-disc-gold'
                : 'hover:text-disc-gold'
            }`}
          >
            Messages
          </Link>
          <Link
            to="/profile"
            className={`font-semibold transition ${
              isActive('/profile')
                ? 'text-disc-gold'
                : 'hover:text-disc-gold'
            }`}
          >
            Profile
          </Link>
          <button
            onClick={handleLogout}
            className="bg-disc-purple hover:bg-disc-purple/80 px-4 py-2 rounded-lg font-semibold transition"
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
  );
}
