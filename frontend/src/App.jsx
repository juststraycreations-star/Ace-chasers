import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
import AuthProvider from './components/AuthProvider';
import Navigation from './components/Navigation';
import EmailVerificationBanner from './components/EmailVerificationBanner';
import Discovery from './pages/Discovery';
import Messages from './pages/Messages';
import Profile from './pages/Profile';
import Likes from './pages/Likes';
import Login from './pages/Login';
import SignUp from './pages/SignUp';

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

      <Routes>
        {!isAuthenticated ? (
          <>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<SignUp />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </>
        ) : (
          <>
            <Route path="/discovery" element={<Discovery />} />
            <Route path="/likes" element={<Likes />} />
            <Route path="/messages" element={<Messages />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="*" element={<Navigate to="/discovery" replace />} />
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
        <AppRoutes />
      </AuthProvider>
    </Router>
  );
}

export default App;
