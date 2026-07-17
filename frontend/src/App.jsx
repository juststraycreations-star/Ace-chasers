import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
import AuthProvider from './components/AuthProvider';
import Navigation from './components/Navigation';
import EmailVerificationBanner from './components/EmailVerificationBanner';
import OnboardingGate from './components/OnboardingGate';
import Discovery from './pages/Discovery';
import Feed from './pages/Feed';
import BagCheck from './pages/BagCheck';
import Courses from './pages/Courses';
import CourseDetail from './pages/CourseDetail';
import DailyPlastic from './pages/DailyPlastic';
import Messages from './pages/Messages';
import Profile from './pages/Profile';
import PlayerProfile from './pages/PlayerProfile';
import Likes from './pages/Likes';
import Login from './pages/Login';
import SignUp from './pages/SignUp';
import LeagueDashboard from './pages/leagues/LeagueDashboard';
import CreateLeague from './pages/leagues/CreateLeague';
import LeagueDetail from './pages/leagues/LeagueDetail';
import RoundScorecard from './pages/leagues/RoundScorecard';
import LeaguePlayerProfile from './pages/leagues/LeaguePlayerProfile';
import Privacy from './pages/legal/Privacy';
import { AuthProvider as LeagueAuthProvider } from './context/AuthContext';

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

      <Routes>
        {!isAuthenticated ? (
          <>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<SignUp />} />
            <Route path="/legal/privacy" element={<Privacy />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </>
        ) : (
          <>
            <Route path="/legal/privacy" element={<Privacy />} />
            <Route path="/feed" element={<Feed />} />
            <Route path="/bagcheck" element={<BagCheck />} />
            <Route path="/courses" element={<Courses />} />
            <Route path="/courses/:id" element={<CourseDetail />} />
            <Route path="/daily-plastic" element={<DailyPlastic />} />
            <Route path="/discovery" element={<Discovery />} />
            <Route path="/likes" element={<Likes />} />
            <Route path="/messages" element={<Messages />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/players/:uid" element={<PlayerProfile />} />
            <Route path="/leagues" element={<LeagueDashboard />} />
            <Route path="/leagues/new" element={<CreateLeague />} />
            <Route path="/leagues/:leagueId" element={<LeagueDetail />} />
            <Route path="/leagues/:leagueId/players/:userId" element={<LeaguePlayerProfile />} />
            <Route path="/rounds/:roundId" element={<RoundScorecard />} />
            <Route path="*" element={<Navigate to="/feed" replace />} />
          </>
        )}
      </Routes>
    </div>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <LeagueAuthProvider>
          <AppRoutes />
        </LeagueAuthProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
