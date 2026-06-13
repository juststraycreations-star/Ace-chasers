import { Link, useLocation, useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { firebaseConfigured, getFirebaseAuth } from '../lib/firebase';
import { clearDevSession } from '../lib/devAuth';

export default function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const reset = useAuthStore((s) => s.reset);

  const isActive = (path) => location.pathname === path;
  const linkClasses = (path) =>
    `font-semibold transition ${isActive(path) ? 'text-disc-gold' : 'hover:text-disc-gold'}`;

  const handleLogout = async () => {
    if (firebaseConfigured) {
      try {
        await signOut(getFirebaseAuth());
      } catch (err) {
        console.warn('sign-out failed', err);
      }
    } else {
      clearDevSession();
    }
    reset();
    navigate('/login');
  };

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
