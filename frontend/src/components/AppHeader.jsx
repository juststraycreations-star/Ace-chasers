import { useAuth } from "@/context/AuthContext";
import { Link, useNavigate } from "react-router-dom";
import { Trophy, SignOut, House, Plus } from "@phosphor-icons/react";

export default function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-30 glass border-b border-white/5">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/leagues" data-testid="header-home-link" className="flex items-center gap-3 group">
          <div className="w-9 h-9 rounded-lg bg-[#F5C542] flex items-center justify-center shadow-[0_0_24px_-4px_rgba(255,92,0,0.7)]">
            <Trophy size={20} weight="fill" color="#0a0a0a" />
          </div>
          <div>
            <div className="font-display text-lg leading-none tracking-tight">Ace Chasers</div>
            <div className="font-mono-data text-[10px] text-zinc-500 mt-1">LEAGUE OPS</div>
          </div>
        </Link>

        <nav className="flex items-center gap-3">
          <button
            data-testid="header-dashboard-btn"
            onClick={() => navigate("/leagues")}
            className="hidden sm:flex items-center gap-2 text-sm text-zinc-300 hover:text-white px-3 py-2 rounded-lg hover:bg-white/5"
          >
            <House size={16} weight="duotone" /> Leagues
          </button>
          <button
            data-testid="header-create-league-btn"
            onClick={() => navigate("/leagues/new")}
            className="btn-primary text-sm flex items-center gap-2"
          >
            <Plus size={16} weight="bold" /> Create League
          </button>
          {user && (
            <div className="flex items-center gap-3 pl-3 ml-1 border-l border-white/10">
              {user.picture ? (
                <img src={user.picture} alt="" className="w-8 h-8 rounded-full" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center text-xs font-bold">
                  {user.name?.charAt(0)}
                </div>
              )}
              <button
                data-testid="header-logout-btn"
                onClick={logout}
                className="text-zinc-400 hover:text-white p-1"
                title="Log out"
              >
                <SignOut size={18} weight="duotone" />
              </button>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
