import { useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { useAuthStore } from '../store/authStore';
import { useMatchStore } from '../store/matchStore';
import { firebaseConfigured, getFirebaseAuth } from '../lib/firebase';
import { clearDevSession } from '../lib/devAuth';
import DiscIcon from './DiscIcon';
import NotificationsBell from './NotificationsBell';
import SessionRequestsModal from './SessionRequestsModal';

const INBOX_POLL_MS = 30_000;

export default function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const reset = useAuthStore((s) => s.reset);
  const user = useAuthStore((s) => s.user);
  const fetchInbox = useMatchStore((s) => s.fetchInbox);

  // Poll the inbox so the bell badge stays roughly up to date without
  // websockets. 60s is enough for an alpha; tighten if it ever matters.
  useEffect(() => {
    if (!user) return undefined;
    fetchInbox();
    const id = setInterval(fetchInbox, INBOX_POLL_MS);
    return () => clearInterval(id);
  }, [user, fetchInbox]);

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
        <Link to="/feed" className="text-2xl font-bold flex items-center gap-2" data-testid="nav-logo">
          <DiscIcon className="h-7 w-7" />
          <span>Ace Chasers</span>
        </Link>

        <div className="flex gap-6 items-center">
          <Link to="/feed" className={linkClasses('/feed')} data-testid="nav-feed">
            Feed
          </Link>
          <Link to="/bagcheck" className={linkClasses('/bagcheck')} data-testid="nav-bagcheck">
            Bag Check
          </Link>
          <Link to="/courses" className={linkClasses('/courses')} data-testid="nav-courses">
            Courses
          </Link>
          <Link to="/discovery" className={linkClasses('/discovery')} data-testid="nav-discovery">
            Discovery
          </Link>
          <Link
            to="/daily-plastic"
            className={linkClasses('/daily-plastic')}
            data-testid="nav-daily-plastic"
          >
            📰 Daily Plastic
          </Link>
          <Link to="/messages" className={linkClasses('/messages')} data-testid="nav-messages">
            Messages
          </Link>
          <Link to="/profile" className={linkClasses('/profile')} data-testid="nav-profile">
            Profile
          </Link>
          <NotificationsBell />
          <button
            onClick={handleLogout}
            className="bg-disc-purple hover:bg-disc-purple/80 px-4 py-2 rounded-lg font-semibold transition"
            data-testid="nav-logout"
          >
            Logout
          </button>
        </div>
      </div>
      <SessionRequestsModal />
    </nav>
  );
}
