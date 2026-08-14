import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';
import { useAuthStore } from './store/authStore';
import AuthProvider from './components/AuthProvider';
import Navigation from './components/Navigation';
import EmailVerificationBanner from './components/EmailVerificationBanner';
import OnboardingGate from './components/OnboardingGate';
import FirstRunWelcomeModal from './components/FirstRunWelcomeModal';
import RouteErrorBoundary from './components/RouteErrorBoundary';
import { Toaster } from './components/ui/sonner';
import { startBuildVersionWatcher } from './lib/buildVersion';
// Login + SignUp stay eager — they are the first paint for logged-out
// visitors so shipping them in the initial bundle saves a round-trip.
// Every other page is code-split via React.lazy.
import Login from './pages/Login';
import SignUp from './pages/SignUp';
import { AuthProvider as LeagueAuthProvider } from './context/AuthContext';

// Route-based lazy chunks — each page downloads only when navigated to.
const Discovery = lazy(() => import('./pages/Discovery'));
const Feed = lazy(() => import('./pages/Feed'));
const BagCheck = lazy(() => import('./pages/BagCheck'));
const Courses = lazy(() => import('./pages/Courses'));
const CourseDetail = lazy(() => import('./pages/CourseDetail'));
const DailyPlastic = lazy(() => import('./pages/DailyPlastic'));
const Messages = lazy(() => import('./pages/Messages'));
const Profile = lazy(() => import('./pages/Profile'));
const PlayerProfile = lazy(() => import('./pages/PlayerProfile'));
const Likes = lazy(() => import('./pages/Likes'));
const LeagueDashboard = lazy(() => import('./pages/leagues/LeagueDashboard'));
const CreateLeague = lazy(() => import('./pages/leagues/CreateLeague'));
const LeagueDetail = lazy(() => import('./pages/leagues/LeagueDetail'));
const RoundScorecard = lazy(() => import('./pages/leagues/RoundScorecard'));
const ThrowTracker = lazy(() => import('./pages/ThrowTracker'));
const LifetimeVault = lazy(() => import('./pages/LifetimeVault'));
const RoundCheckin = lazy(() => import('./pages/RoundCheckin'));
const LeaguePlayerProfile = lazy(() => import('./pages/leagues/LeaguePlayerProfile'));
const Privacy = lazy(() => import('./pages/legal/Privacy'));
const Beta = lazy(() => import('./pages/Beta'));
const BetaTestersAdmin = lazy(() => import('./pages/BetaTestersAdmin'));

const RouteFallback = () => (
  <div
    className="min-h-[60vh] flex items-center justify-center text-gray-500 font-mono-data text-xs tracking-wider"
    data-testid="route-loading"
  >
    LOADING…
  </div>
);

function AppRoutes() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authReady = useAuthStore((s) => s.authReady);

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500" data-testid="app-loading">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {isAuthenticated && <Navigation />}
      {isAuthenticated && <EmailVerificationBanner />}
      {isAuthenticated && <OnboardingGate />}
      {isAuthenticated && <FirstRunWelcomeModal />}

      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {!isAuthenticated ? (
            <>
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<SignUp />} />
              <Route path="/legal/privacy" element={<Privacy />} />
              <Route path="/beta" element={<Beta />} />
              <Route path="*" element={<Navigate to="/login" replace />} />
            </>
          ) : (
            <>
              <Route path="/legal/privacy" element={<Privacy />} />
              <Route path="/beta" element={<Beta />} />
              <Route path="/admin/beta-testers" element={<BetaTestersAdmin />} />
              <Route path="/feed" element={<Feed />} />
              <Route path="/bagcheck" element={<BagCheck />} />
              <Route path="/courses" element={<Courses />} />
              <Route path="/courses/:id" element={<CourseDetail />} />
              <Route path="/daily-plastic" element={<DailyPlastic />} />
              <Route
                path="/discovery"
                element={
                  <RouteErrorBoundary name="Discovery">
                    <Discovery />
                  </RouteErrorBoundary>
                }
              />
              <Route path="/likes" element={<Likes />} />
              <Route path="/messages" element={<Messages />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/players/:uid" element={<PlayerProfile />} />
              <Route path="/leagues" element={<LeagueDashboard />} />
              <Route path="/leagues/new" element={<CreateLeague />} />
              <Route path="/leagues/:leagueId" element={<LeagueDetail />} />
              <Route path="/leagues/:leagueId/players/:userId" element={<LeaguePlayerProfile />} />
              <Route path="/rounds/:roundId" element={<RoundScorecard />} />
              <Route path="/throws" element={<ThrowTracker />} />
              <Route path="/vault" element={<LifetimeVault />} />
              <Route path="/rounds/:roundId/checkin" element={<RoundCheckin />} />
              <Route path="*" element={<Navigate to="/feed" replace />} />
            </>
          )}
        </Routes>
      </Suspense>
    </div>
  );
}

function App() {
  useEffect(() => { startBuildVersionWatcher(); }, []);
  return (
    <Router>
      <AuthProvider>
        <LeagueAuthProvider>
          <AppRoutes />
          <Toaster richColors position="top-right" />
        </LeagueAuthProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
