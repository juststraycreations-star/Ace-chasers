import { Link, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export default function Navigation() {
  const location = useLocation();
  const logout = useAuthStore((state) => state.logout);

  const isActive = (path) => location.pathname === path;

  const handleLogout = () => {
    logout();
  };

  const linkClasses = (path) =>
    `font-semibold transition ${
      isActive(path) ? 'text-disc-gold' : 'hover:text-disc-gold'
    }`;

  return (
    <nav className="bg-disc-green text-white shadow-lg sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center">
        <Link to="/discovery" className="text-2xl font-bold" data-testid="nav-logo">
          ⛳ Ace Chasers
        </Link>

        <div className="flex gap-6 items-center">
          <Link to="/discovery" className={linkClasses('/discovery')} data-testid="nav-discovery">
            Discovery
          </Link>
          <Link to="/likes" className={linkClasses('/likes')} data-testid="nav-likes">
            Likes
          </Link>
          <Link to="/messages" className={linkClasses('/messages')} data-testid="nav-messages">
            Messages
          </Link>
          <Link to="/profile" className={linkClasses('/profile')} data-testid="nav-profile">
            Profile
          </Link>
          <button
            onClick={handleLogout}
            className="bg-disc-purple hover:bg-disc-purple/80 px-4 py-2 rounded-lg font-semibold transition"
            data-testid="nav-logout"
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
  );
}
