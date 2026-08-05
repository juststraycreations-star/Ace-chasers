import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import ReportBugButton from "@/components/ReportBugButton";
import { LeagueGridSkeleton } from "@/components/Skeletons";
import { Plus, MapPin, Users, TrendUp } from "@phosphor-icons/react";
import { toast } from "sonner";

/**
 * League Dashboard — restructured (Session 41):
 *  - Zone 1: Header (title + subline)              — off-white canvas
 *  - Zone 2: Primary action card (New League only) — solid white card
 *  - Zone 3: League list, each row a bounded card  — solid white cards
 *  - Zone 4: Browse public leagues                 — separated section
 *  - Footer:  quiet Report a Bug link
 */
export default function Dashboard() {
  const navigate = useNavigate();
  const [myLeagues, setMyLeagues] = useState([]);
  const [browse, setBrowse] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    // Use allSettled so a broken /leagues/browse (e.g. 500) doesn't
    // suppress the /leagues data or fire a scary top-level toast.
    const [mineRes, allRes] = await Promise.allSettled([
      api.get("/leagues"),
      api.get("/leagues/browse"),
    ]);
    let mineIds = new Set();
    if (mineRes.status === "fulfilled") {
      setMyLeagues(mineRes.value.data);
      mineIds = new Set(mineRes.value.data.map((l) => l.id));
    } else {
      toast.error("Failed to load your leagues");
    }
    if (allRes.status === "fulfilled") {
      setBrowse(allRes.value.data.filter((l) => !mineIds.has(l.id)));
    } else {
      setBrowse([]);
    }
    setLoading(false);
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
    <div className="min-h-screen bg-gray-50" data-testid="dashboard-page">
      <AppHeader />
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-10">
        {/* Zone 1 — Header */}
        <header className="mb-6" data-testid="dashboard-header">
          <div className="font-mono-data text-xs text-zinc-500 mb-2">MY DASHBOARD</div>
          <h1 className="font-display text-4xl sm:text-5xl tracking-tighter text-gray-900">
            Your Leagues
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            Manage every league you run or play in, then jump into an active round.
          </p>
        </header>

        <hr className="border-gray-200 mb-6" />

        {/* Zone 2 — Primary action card (New League only) */}
        <section
          className="bg-white border border-gray-100 rounded-2xl shadow-sm p-5 sm:p-6 mb-8"
          data-testid="dashboard-primary-action"
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="font-mono-data text-[10px] uppercase tracking-[0.2em] text-amber-600 mb-1">
                Start a new season
              </div>
              <h2 className="font-display text-xl text-gray-900">Create a league</h2>
              <p className="text-sm text-gray-500 mt-1">
                Set the format, invite players, and start posting rounds in under two minutes.
              </p>
            </div>
            <button
              data-testid="dashboard-create-league-btn"
              onClick={() => navigate("/leagues/new")}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-[#1f4d2e] hover:bg-[#173d24] text-white font-semibold text-sm px-6 py-3 shadow-md shadow-emerald-900/10 transition-all duration-200 hover:scale-[1.02] active:scale-95 w-full sm:w-auto"
            >
              <Plus size={16} weight="bold" /> New League
            </button>
          </div>
        </section>

        {/* Zone 3 — League list */}
        {loading && <LeagueGridSkeleton count={4} />}

        {!loading && myLeagues.length === 0 && (
          <div
            className="bg-white border border-gray-100 rounded-2xl shadow-sm p-10 text-center"
            data-testid="dashboard-empty-state"
          >
            <div className="font-display text-2xl text-gray-900 mb-2">No leagues yet</div>
            <div className="text-gray-500 mb-6">
              Create your first league above or join one from the public list below.
            </div>
          </div>
        )}

        {!loading && myLeagues.length > 0 && (
          <div className="space-y-3" data-testid="dashboard-league-list">
            {myLeagues.map((l) => (
              <button
                key={l.id}
                data-testid={`dashboard-league-card-${l.id}`}
                onClick={() => navigate(`/leagues/${l.id}`)}
                className="w-full bg-white border border-gray-100 rounded-2xl shadow-sm hover:shadow-md hover:border-amber-500/40 transition-all duration-200 p-5 sm:p-6 text-left group"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  {/* Left — descriptive stack */}
                  <div className="min-w-0 flex-1">
                    <div className="font-display text-xl text-gray-900 group-hover:text-[#1f4d2e] transition-colors truncate">
                      {l.name}
                    </div>
                    <div className="mt-1.5 flex items-center gap-1.5 text-sm text-gray-600">
                      <MapPin size={14} weight="duotone" className="text-gray-400" />
                      <span className="truncate">{l.location}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-xs text-gray-500">
                      <Users size={13} weight="duotone" className="text-gray-400" />
                      <span>{l.member_count} players</span>
                    </div>
                  </div>

                  {/* Right — metric stack */}
                  <div className="flex sm:flex-col items-start sm:items-end gap-3 sm:gap-1.5 sm:text-right shrink-0">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-amber-50 border border-amber-100 text-[10px] font-mono-data tracking-wider uppercase text-amber-700">
                      {l.format}
                    </span>
                    <div className="font-mono-data text-[10px] tracking-wider uppercase text-gray-500">
                      Ace Pool
                    </div>
                    <div className="font-display text-lg text-amber-600 leading-none">
                      ${(l.ace_pool || 0).toFixed(0)}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Zone 4 — Browse */}
        {browse.length > 0 && (
          <section className="mt-14" data-testid="dashboard-browse-section">
            <hr className="border-gray-200 mb-6" />
            <div className="mb-4">
              <div className="font-mono-data text-xs text-zinc-500 mb-2">DISCOVER</div>
              <h2 className="font-display text-2xl text-gray-900">Browse Public Leagues</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {browse.map((l) => (
                <div
                  key={l.id}
                  className="bg-white border border-gray-100 rounded-2xl shadow-sm p-5"
                  data-testid={`browse-league-${l.id}`}
                >
                  <div className="font-display text-lg text-gray-900 mb-1">{l.name}</div>
                  <div className="text-sm text-gray-600 flex items-center gap-1"><MapPin size={14} /> {l.location}</div>
                  <div className="mt-3 text-xs text-gray-500 flex items-center gap-2">
                    <TrendUp size={14} /> {l.member_count} players · {l.format}
                  </div>
                  <button
                    data-testid={`browse-join-btn-${l.id}`}
                    onClick={() => join(l.id)}
                    className="mt-4 w-full py-2 border border-gray-200 rounded-full text-sm hover:border-[#1f4d2e] hover:text-[#1f4d2e] transition-colors"
                  >Join League</button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Footer — quiet bug link */}
        <footer
          className="mt-16 pt-6 border-t border-gray-200 flex justify-center"
          data-testid="dashboard-footer"
        >
          <ReportBugButton variant="muted" />
        </footer>
      </main>
    </div>
  );
}
