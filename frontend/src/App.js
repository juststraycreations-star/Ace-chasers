import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, useNavigate, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import CreateLeague from "@/pages/CreateLeague";
import LeagueDetail from "@/pages/LeagueDetail";
import RoundScorecard from "@/pages/RoundScorecard";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
function AuthCallback() {
  const navigate = useNavigate();
  useEffect(() => {
    const processCallback = async () => {
      const hash = window.location.hash;
      const params = new URLSearchParams(hash.replace(/^#/, ""));
      const session_id = params.get("session_id");
      if (!session_id) {
        navigate("/", { replace: true });
        return;
      }
      try {
        const { data } = await api.post("/auth/session", { session_id });
        if (data?.session_token) {
          localStorage.setItem("session_token", data.session_token);
        }
        // Clear the hash and go to dashboard
        window.history.replaceState(null, "", "/dashboard");
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch (e) {
        console.error("Session exchange failed", e);
        navigate("/", { replace: true });
      }
    };
    processCallback();
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#09090B] text-white">
      <div className="text-center">
        <div className="w-12 h-12 border-2 border-[#FF5C00] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="font-mono-data text-xs text-zinc-400">Signing you in…</p>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090B]">
        <div className="w-10 h-10 border-2 border-[#FF5C00] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }
  if (!user) return <Navigate to="/" replace />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/create-league" element={<ProtectedRoute><CreateLeague /></ProtectedRoute>} />
      <Route path="/leagues/:leagueId" element={<ProtectedRoute><LeagueDetail /></ProtectedRoute>} />
      <Route path="/rounds/:roundId" element={<ProtectedRoute><RoundScorecard /></ProtectedRoute>} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App min-h-screen">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster theme="dark" position="top-right" />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
