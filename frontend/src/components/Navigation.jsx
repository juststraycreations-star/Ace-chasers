import { useEffect, useState } from 'react';
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

const NAV_ITEMS = [
  { to: '/feed', label: 'Feed', testid: 'nav-feed' },
  { to: '/bagcheck', label: 'Bag Check', testid: 'nav-bagcheck' },
  { to: '/courses', label: 'Courses', testid: 'nav-courses' },
  { to: '/discovery', label: 'Discovery', testid: 'nav-discovery' },
  { to: '/daily-plastic', label: '📰 Daily Plastic', testid: 'nav-daily-plastic' },
  { to: '/messages', label: 'Messages', testid: 'nav-messages' },
  { to: '/profile', label: 'Profile', testid: 'nav-profile' },
];

export default function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const reset = useAuthStore((s) => s.reset);
  const user = useAuthStore((s) => s.user);
  const fetchInbox = useMatchStore((s) => s.fetchInbox);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!user) return undefined;
    fetchInbox();
    const id = setInterval(fetchInbox, INBOX_POLL_MS);
    return () => clearInterval(id);
  }, [user, fetchInbox]);

  // Close mobile menu when route changes
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const isActive = (path) => location.pathname === path;
  const linkClasses = (path) =>
    `font-semibold transition ${isActive(path) ? 'text-disc-gold' : 'hover:text-disc-gold'}`;
  const mobileLinkClasses = (path) =>
    `block py-3 px-4 rounded-lg font-semibold transition ${
      isActive(path)
        ? 'bg-disc-gold/20 text-disc-gold'
        : 'text-white hover:bg-white/10 hover:text-disc-gold'
    }`;

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
    setMobileOpen(false);
    navigate('/login');
  };

  return (
    <nav className="bg-disc-green text-white shadow-lg sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center gap-3">
        <Link
          to="/feed"
          className="text-xl sm:text-2xl font-bold flex items-center gap-2 min-w-0"
          data-testid="nav-logo"
        >
          <DiscIcon className="h-6 w-6 sm:h-7 sm:w-7 flex-shrink-0" />
          <span className="truncate">Ace Chasers</span>
        </Link>

        {/* Desktop nav (lg and up) */}
        <div className="hidden lg:flex gap-6 items-center">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={linkClasses(item.to)}
              data-testid={item.testid}
            >
              {item.label}
            </Link>
          ))}
          <NotificationsBell />
          <button
            onClick={handleLogout}
            className="bg-disc-purple hover:bg-disc-purple/80 px-4 py-2 rounded-lg font-semibold transition"
            data-testid="nav-logout"
          >
            Logout
          </button>
        </div>

        {/* Mobile right cluster (below lg) */}
        <div className="flex lg:hidden items-center gap-2">
          <NotificationsBell />
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
            className="p-2 rounded-lg hover:bg-white/10 transition focus:outline-none focus:ring-2 focus:ring-disc-gold"
            data-testid="nav-mobile-toggle"
          >
            {mobileOpen ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile dropdown panel */}
      {mobileOpen && (
        <div
          className="lg:hidden bg-disc-green border-t border-white/10 shadow-lg"
          data-testid="nav-mobile-panel"
        >
          <div className="max-w-6xl mx-auto px-4 py-3 space-y-1">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={mobileLinkClasses(item.to)}
                data-testid={`${item.testid}-mobile`}
                onClick={() => setMobileOpen(false)}
              >
                {item.label}
              </Link>
            ))}
            <button
              onClick={handleLogout}
              className="w-full text-left bg-disc-purple hover:bg-disc-purple/80 py-3 px-4 rounded-lg font-semibold transition mt-2"
              data-testid="nav-logout-mobile"
            >
              Logout
            </button>
          </div>
        </div>
      )}

      <SessionRequestsModal />
    </nav>
  );
}
