import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import StandingsTab from "@/components/StandingsTab";
import LedgerTab from "@/components/LedgerTab";
import ClubhouseTab from "@/components/ClubhouseTab";
import ComplianceTab from "@/components/ComplianceTab";
import DeleteLeaguePanel from "@/components/DeleteLeaguePanel";
import ManagerDMPanel from "@/components/ManagerDMPanel";
import RoundQRPanel from "@/components/RoundQRPanel";
import RoundCard from "@/components/RoundCard";
import BracketView from "@/components/BracketView";
import ClubhouseAgreementModal from "@/components/ClubhouseAgreementModal";
import { useAuth } from "@/context/AuthContext";
import LeagueLiveNotifier from "@/components/LeagueLiveNotifier";
import { MapPin, Users, Trophy, Coins, ChatCircle, Calendar, Plus, PlayCircle, CheckCircle, QrCode, ShieldCheck } from "@phosphor-icons/react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";

export default function LeagueDetail() {
  const { leagueId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Default landing tab is now the Clubhouse feed (matches the main social
  // feed UX), so a member opening their league page lands directly on the
  // conversation. `?tab=rounds` (or any other key) still short-circuits back
  // to the original layout when needed.
  const initialTab = searchParams.get("tab") || "clubhouse";
  const [league, setLeague] = useState(null);
  const [rounds, setRounds] = useState([]);
  const [members, setMembers] = useState([]);
  const [seasons, setSeasons] = useState([]);
  const [tab, setTab] = useState(initialTab);
  const [completedOpen, setCompletedOpen] = useState(false);
  const [showQR, setShowQR] = useState(false);
  // "New Round" modal state — director-only
  const [showNewRound, setShowNewRound] = useState(false);
  // Which round the manager is currently displaying a QR panel for.
  const [qrRoundId, setQrRoundId] = useState(null);
  const [newRound, setNewRound] = useState({
    name: "",
    date: new Date().toISOString().slice(0, 10),
    holes: 18,
    course_rating: "",
    course_location: "",
    publish_announcement: true,
  });
  const [creatingRound, setCreatingRound] = useState(false);

  const load = async () => {
    try {
      // Single bundled call replaces the previous 4 parallel GETs. Same
      // shapes on the client — league / rounds / members / seasons.
      const { data } = await api.get(`/leagues/${leagueId}/dashboard`);
      setLeague(data.league);
      setRounds(data.rounds);
      setMembers(data.members);
      setSeasons(data.seasons);
    } catch (e) {
      toast.error("Failed to load league");
    }
  };
  useEffect(() => { load(); }, [leagueId]);

  const join = async () => {
    try { await api.post(`/leagues/${leagueId}/join`); toast.success("Joined!"); await load(); }
    catch { toast.error("Failed to join"); }
  };

  const startRound = async (roundId) => {
    try { await api.patch(`/rounds/${roundId}/status`, { status: "active" }); await load(); }
    catch { toast.error("Failed"); }
  };
  const completeRound = async (roundId) => {
    try { await api.patch(`/rounds/${roundId}/status`, { status: "completed" }); await load(); toast.success("Round finalized"); }
    catch { toast.error("Failed"); }
  };

  const createRound = async () => {
    // Director-only. Requires an active season — league creation seeds
    // one automatically so we can just take the first one.
    if (!newRound.name.trim()) { toast.error("Give the round a name"); return; }
    if (!newRound.date) { toast.error("Pick a date"); return; }
    const seasonId = seasons[0]?.id;
    if (!seasonId) { toast.error("This league has no active season yet"); return; }
    setCreatingRound(true);
    try {
      const payload = {
        season_id: seasonId,
        name: newRound.name.trim(),
        date: newRound.date,
        holes: Number(newRound.holes) || 18,
        publish_announcement: newRound.publish_announcement,
      };
      if (newRound.course_rating) payload.course_rating = Number(newRound.course_rating);
      if (newRound.course_location) payload.course_location = newRound.course_location.trim();
      const { data } = await api.post(`/leagues/${leagueId}/rounds`, payload);
      toast.success(newRound.publish_announcement
        ? "Round created · pinned to feed"
        : "Round created");
      setShowNewRound(false);
      setNewRound({
        name: "",
        date: new Date().toISOString().slice(0, 10),
        holes: 18,
        course_rating: "",
        course_location: "",
        publish_announcement: true,
      });
      // Take the director straight to the scorecard so they can build cards
      navigate(`/rounds/${data.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create round");
    } finally {
      setCreatingRound(false);
    }
  };

  if (!league) return (
    <div className="min-h-screen bg-white"><AppHeader /><div className="max-w-7xl mx-auto p-10 text-zinc-500 font-mono-data text-xs">LOADING…</div></div>
  );

  const checkInUrl = `${window.location.origin}/leagues/${leagueId}?join=1`;

  const tabs = [
    { key: "rounds", label: "Rounds", icon: <Calendar size={15} /> },
    ...(league.format === "Match Play"
      ? [{ key: "bracket", label: "Bracket", icon: <Trophy size={15} /> }]
      : []),
    { key: "standings", label: "Standings", icon: <Trophy size={15} /> },
    { key: "ledger", label: "Ledger", icon: <Coins size={15} /> },
    { key: "clubhouse", label: "Clubhouse", icon: <ChatCircle size={15} /> },
    ...(league.is_director
      ? [{ key: "compliance", label: "Compliance", icon: <ShieldCheck size={15} /> }]
      : []),
  ];

  return (
    <div className="min-h-screen bg-white" data-testid="league-detail-page">
      <AppHeader />
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="card-surface p-6 sm:p-8 mb-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 px-2.5 py-0.5 text-[10px] font-mono-data uppercase tracking-widest font-semibold">{league.format}</div>
                {league.is_director && (
                  <div className="inline-flex items-center gap-1 rounded-full bg-emerald-600 text-white px-2.5 py-0.5 text-[10px] font-mono-data uppercase tracking-widest font-semibold">
                    <ShieldCheck size={11} weight="fill" /> Director
                  </div>
                )}
              </div>
              <h1 className="font-display text-4xl sm:text-5xl tracking-tighter text-slate-900">{league.name}</h1>
              {/* Signature Ace Chasers badge-chip row — replaces the flat metadata line. */}
              <div className="mt-4 flex flex-wrap items-center gap-2" data-testid="league-meta-chips">
                <span
                  data-testid="league-chip-location"
                  className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm"
                >
                  <MapPin size={13} weight="duotone" className="text-emerald-600" />
                  {league.location}
                </span>
                <span
                  data-testid="league-chip-players"
                  className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm"
                >
                  <Users size={13} weight="duotone" className="text-emerald-600" />
                  {league.member_count} player{league.member_count === 1 ? "" : "s"}
                </span>
                <span
                  data-testid="league-chip-ace-pool"
                  className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm font-mono-data"
                >
                  <Coins size={13} weight="duotone" className="text-emerald-600" />
                  ACE POOL <span className="text-emerald-700">${(league.ace_pool || 0).toFixed(0)}</span>
                </span>
                <span
                  data-testid="league-chip-bag-tag"
                  className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm font-mono-data"
                >
                  <Trophy size={13} weight="duotone" className="text-emerald-600" />
                  BAG TAG <span className="text-emerald-700">{league.my_bag_tag ? `#${league.my_bag_tag}` : "—"}</span>
                </span>
              </div>
              {league.description && <p className="mt-4 text-sm text-slate-600 max-w-2xl">{league.description}</p>}
            </div>
            <div className="flex flex-col gap-2">
              {league.is_member && (
                <LeagueLiveNotifier leagueId={leagueId} isDirector={league.is_director} />
              )}
              {!league.is_member && (
                <button data-testid="league-join-btn" onClick={join} className="btn-primary">Join League</button>
              )}
              {league.is_member && (
                <button data-testid="league-qr-btn" onClick={() => setShowQR(!showQR)} className="btn-primary flex items-center gap-2">
                  <QrCode size={16} weight="bold" /> Check-In QR
                </button>
              )}
            </div>
          </div>

          {showQR && (
            <div className="mt-6 flex flex-col items-center p-6 bg-white rounded-lg" data-testid="qr-container">
              <QRCodeSVG value={checkInUrl} size={200} bgColor="#ffffff" fgColor="#0a0a0a" />
              <div className="font-mono-data text-[10px] text-zinc-800 mt-3 text-center">
                CHECK-IN URL<br />
                <span className="text-zinc-600">{checkInUrl}</span>
              </div>
            </div>
          )}
        </div>

        {/* Manager comms — DM + broadcast, director-only */}
        {league.is_director && (
          <div className="mb-6" data-testid="manager-comms-wrapper">
            <ManagerDMPanel leagueId={leagueId} isDirector={league.is_director} />
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-6 overflow-x-auto pb-1" data-testid="league-tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              data-testid={`tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-full text-sm font-semibold flex items-center gap-2 flex-shrink-0 transition-colors ${
                tab === t.key
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "bg-white text-slate-700 border border-slate-200 hover:border-slate-400"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {tab === "rounds" && (
          <div className="space-y-6" data-testid="rounds-tab">
            {league.is_director && (
              <div className="flex justify-end">
                <button
                  data-testid="new-round-btn"
                  onClick={() => setShowNewRound(true)}
                  className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm px-4 py-2 shadow-sm transition-colors"
                >
                  <Plus size={16} weight="bold" /> New Round
                </button>
              </div>
            )}

            {(() => {
              const active = rounds.filter((r) => r.status === "active");
              const upcoming = rounds.filter((r) => r.status === "scheduled");
              const completed = rounds.filter((r) => r.status === "completed");
              return (
                <>
                  {/* ═══ ACTIVE ROUND ═══ */}
                  {active.length > 0 && (
                    <section data-testid="rounds-active-section">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        <h2 className="font-display text-sm uppercase tracking-widest text-emerald-800">Active Round</h2>
                      </div>
                      {active.map((r) => (
                        <RoundCard
                          key={r.id}
                          variant="active"
                          round={r}
                          isDirector={league.is_director}
                          qrOpen={qrRoundId === r.id}
                          onOpenScorecard={() => navigate(`/rounds/${r.id}`)}
                          onFinalize={() => completeRound(r.id)}
                          onToggleQR={() => setQrRoundId(qrRoundId === r.id ? null : r.id)}
                        />
                      ))}
                    </section>
                  )}

                  {/* ═══ UPCOMING SCHEDULE ═══ */}
                  <section data-testid="rounds-upcoming-section">
                    <h2 className="font-display text-sm uppercase tracking-widest text-slate-700 mb-3">
                      Upcoming Schedule
                      <span className="ml-2 font-mono-data text-xs text-slate-400">· {upcoming.length}</span>
                    </h2>
                    {upcoming.length === 0 ? (
                      <div
                        className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500"
                        data-testid="rounds-upcoming-empty"
                      >
                        Nothing scheduled next.
                      </div>
                    ) : (
                      <ul className="space-y-2">
                        {upcoming.map((r) => (
                          <RoundCard
                            key={r.id}
                            variant="upcoming"
                            round={r}
                            isDirector={league.is_director}
                            onOpenScorecard={() => navigate(`/rounds/${r.id}`)}
                            onStart={() => startRound(r.id)}
                          />
                        ))}
                      </ul>
                    )}
                  </section>

                  {/* ═══ COMPLETED ARCHIVE ═══ */}
                  {completed.length > 0 && (
                    <section data-testid="rounds-completed-section">
                      <button
                        type="button"
                        onClick={() => setCompletedOpen((v) => !v)}
                        data-testid="rounds-completed-toggle"
                        aria-expanded={completedOpen}
                        className="w-full flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 hover:bg-slate-50 transition-colors"
                      >
                        <h2 className="font-display text-sm uppercase tracking-widest text-slate-700">
                          Completed Archive
                          <span className="ml-2 font-mono-data text-xs text-slate-400">· {completed.length}</span>
                        </h2>
                        <span className="text-xs font-semibold text-slate-600">
                          {completedOpen ? "Hide" : "Show"}
                        </span>
                      </button>
                      {completedOpen && (
                        <ul
                          className="mt-2 divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white overflow-hidden"
                          data-testid="rounds-completed-list"
                        >
                          {completed.map((r) => (
                            <RoundCard
                              key={r.id}
                              variant="completed"
                              round={r}
                              onOpenScorecard={() => navigate(`/rounds/${r.id}`)}
                            />
                          ))}
                        </ul>
                      )}
                    </section>
                  )}
                </>
              );
            })()}

            {rounds.length === 0 && (
              <div className="text-slate-500 text-sm text-center py-8" data-testid="rounds-empty-state">
                No rounds scheduled yet
                {league.is_director && (
                  <div className="mt-3">
                    <button
                      data-testid="rounds-empty-create-btn"
                      onClick={() => setShowNewRound(true)}
                      className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs px-4 py-2 shadow-sm transition-colors"
                    >
                      Create your first round
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {tab === "standings" && <StandingsTab leagueId={leagueId} />}
        {tab === "bracket" && (
          <BracketView
            leagueId={leagueId}
            leagueName={league.name}
            members={members}
            isDirector={league.is_director}
            format={league.format}
          />
        )}
        {tab === "ledger" && <LedgerTab leagueId={leagueId} isDirector={league.is_director} />}
        {tab === "clubhouse" && <ClubhouseTab leagueId={leagueId} isDirector={league.is_director} currentUser={user} />}
        {tab === "compliance" && (
          <>
            <ComplianceTab leagueId={leagueId} isDirector={league.is_director} />
            <DeleteLeaguePanel
              leagueId={leagueId}
              leagueName={league.name}
              isDirector={league.is_director}
            />
          </>
        )}

        {/* Fair Play Agreement modal — covers Announcements-only viewers and
            every other private league surface. Renders once per league until
            the member ticks "I Agree". */}
        {league.is_member && league.my_clubhouse_agreed === false && (
          <ClubhouseAgreementModal
            leagueId={leagueId}
            onAgree={() => setLeague((prev) => prev ? { ...prev, my_clubhouse_agreed: true } : prev)}
          />
        )}

        {/* New Round modal (director-only) */}
        {showNewRound && (
          <div
            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => !creatingRound && setShowNewRound(false)}
            data-testid="new-round-modal"
          >
            <div
              className="bg-white rounded-2xl border border-gray-200 max-w-md w-full p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4">
                <div className="font-mono-data text-[10px] text-zinc-500 tracking-wider">SCHEDULE · DIRECTOR</div>
                <div className="font-display text-2xl tracking-tight mt-1">New Round</div>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Round name</label>
                  <input
                    data-testid="new-round-name-input"
                    value={newRound.name}
                    onChange={(e) => setNewRound({ ...newRound, name: e.target.value })}
                    placeholder="Week 3 · Winthrop Park"
                    className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Date</label>
                    <input
                      type="date"
                      data-testid="new-round-date-input"
                      value={newRound.date}
                      onChange={(e) => setNewRound({ ...newRound, date: e.target.value })}
                      className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Holes</label>
                    <select
                      data-testid="new-round-holes-input"
                      value={newRound.holes}
                      onChange={(e) => setNewRound({ ...newRound, holes: Number(e.target.value) })}
                      className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
                    >
                      <option value={9}>9</option>
                      <option value={18}>18</option>
                      <option value={24}>24</option>
                      <option value={27}>27</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Course rating (optional)</label>
                  <input
                    type="number"
                    step="0.1"
                    data-testid="new-round-rating-input"
                    value={newRound.course_rating}
                    onChange={(e) => setNewRound({ ...newRound, course_rating: e.target.value })}
                    placeholder="e.g. 54.5"
                    className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Course location (optional)</label>
                  <input
                    type="text"
                    data-testid="new-round-location-input"
                    value={newRound.course_location}
                    onChange={(e) => setNewRound({ ...newRound, course_location: e.target.value })}
                    placeholder="Maple Hill DGC · Leicester, MA"
                    className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
                  />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    data-testid="new-round-publish-checkbox"
                    checked={newRound.publish_announcement}
                    onChange={(e) => setNewRound({ ...newRound, publish_announcement: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-400"
                  />
                  Publish a pinned announcement on the clubhouse feed
                </label>
                {seasons.length === 0 && (
                  <div className="rounded-md border border-yellow-300 bg-yellow-50 text-[11px] text-yellow-900 p-2">
                    No active season detected — the round will still be created but standings may not compute.
                  </div>
                )}
              </div>
              <div className="mt-5 flex items-center justify-end gap-2">
                <button
                  data-testid="new-round-cancel-btn"
                  onClick={() => setShowNewRound(false)}
                  disabled={creatingRound}
                  className="text-xs px-4 py-2 rounded-lg text-zinc-600 hover:text-gray-900 disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  data-testid="new-round-confirm-btn"
                  onClick={createRound}
                  disabled={creatingRound || !newRound.name.trim() || !newRound.date}
                  className="btn-primary text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {creatingRound ? "Creating…" : "Create Round"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
