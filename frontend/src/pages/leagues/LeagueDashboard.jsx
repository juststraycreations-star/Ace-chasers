import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import { Plus, MapPin, Users, TrendUp } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Dashboard() {
  const navigate = useNavigate();
  const [myLeagues, setMyLeagues] = useState([]);
  const [browse, setBrowse] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [mine, all] = await Promise.all([
        api.get("/leagues"),
        api.get("/leagues/browse"),
      ]);
      setMyLeagues(mine.data);
      const mineIds = new Set(mine.data.map((l) => l.id));
      setBrowse(all.data.filter((l) => !mineIds.has(l.id)));
    } catch (e) {
      toast.error("Failed to load leagues");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const join = async (id) => {
    try {
      await api.post(`/leagues/${id}/join`);
      toast.success("Joined league");
      await load();
      navigate(`/leagues/${id}`);
    } catch { toast.error("Failed to join"); }
  };

  return (
    <div className="min-h-screen bg-white" data-testid="dashboard-page">
      <AppHeader />
      <main className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-2">MY DASHBOARD</div>
            <h1 className="font-display text-4xl sm:text-5xl tracking-tighter">Your Leagues</h1>
          </div>
          <button
            data-testid="dashboard-create-league-btn"
            onClick={() => navigate("/leagues/new")}
            className="btn-primary flex items-center gap-2"
          >
            <Plus size={16} weight="bold" /> New League
          </button>
        </div>

        {loading && <div className="text-zinc-500 font-mono-data text-xs">LOADING…</div>}

        {!loading && myLeagues.length === 0 && (
          <div className="card-surface p-10 text-center">
            <div className="font-display text-2xl mb-2">No leagues yet</div>
            <div className="text-zinc-400 mb-6">Create your first league or join an existing one below.</div>
            <button
              data-testid="dashboard-empty-create-btn"
              onClick={() => navigate("/leagues/new")}
              className="btn-primary"
            >Create a League</button>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {myLeagues.map((l) => (
            <button
              key={l.id}
              data-testid={`dashboard-league-card-${l.id}`}
              onClick={() => navigate(`/leagues/${l.id}`)}
              className="card-surface p-6 text-left hover:border-[#F5C542]/50 transition-colors group"
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="font-display text-xl group-hover:text-[#F5C542] transition-colors">{l.name}</div>
                  <div className="text-sm text-zinc-500 flex items-center gap-1 mt-1">
                    <MapPin size={14} weight="duotone" /> {l.location}
                  </div>
                </div>
                <div className="chip-orange px-2 py-1 rounded-md text-[10px] font-mono-data">
                  {l.format}
                </div>
              </div>
              <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <Users size={14} weight="duotone" /> {l.member_count} players
                </div>
                <div className="font-mono-data text-xs text-zinc-500">
                  ACE POOL <span className="text-[#F5C542]">${(l.ace_pool || 0).toFixed(0)}</span>
                </div>
              </div>
            </button>
          ))}
        </div>

        {browse.length > 0 && (
          <>
            <div className="mt-16 mb-6">
              <div className="font-mono-data text-xs text-zinc-500 mb-2">DISCOVER</div>
              <h2 className="font-display text-2xl">Browse Public Leagues</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {browse.map((l) => (
                <div key={l.id} className="card-surface p-6" data-testid={`browse-league-${l.id}`}>
                  <div className="font-display text-lg mb-1">{l.name}</div>
                  <div className="text-sm text-zinc-500 flex items-center gap-1"><MapPin size={14} /> {l.location}</div>
                  <div className="mt-3 text-xs text-zinc-500 flex items-center gap-2">
                    <TrendUp size={14} /> {l.member_count} players · {l.format}
                  </div>
                  <button
                    data-testid={`browse-join-btn-${l.id}`}
                    onClick={() => join(l.id)}
                    className="mt-4 w-full py-2 border border-gray-200 rounded-full text-sm hover:bg-white/5"
                  >Join League</button>
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
