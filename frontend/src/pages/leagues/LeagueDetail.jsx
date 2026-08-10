import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import StandingsTab from "@/components/StandingsTab";
import LedgerTab from "@/components/LedgerTab";
import ClubhouseTab from "@/components/ClubhouseTab";
import ComplianceTab from "@/components/ComplianceTab";
import ManagerDMPanel from "@/components/ManagerDMPanel";
import RoundQRPanel from "@/components/RoundQRPanel";
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
  const [league, setLeague] = useState(null);
  const [rounds, setRounds] = useState([]);
  const [members, setMembers] = useState([]);
  const [seasons, setSeasons] = useState([]);
  const [tab, setTab] = useState("rounds");
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
                <div className="chip-orange px-2 py-1 rounded-md text-[10px] font-mono-data">{league.format}</div>
                {league.is_director && <div className="chip-green px-2 py-1 rounded-md text-[10px] font-mono-data">DIRECTOR</div>}
              </div>
              <h1 className="font-display text-4xl sm:text-5xl tracking-tighter">{league.name}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-zinc-400">
                <div className="flex items-center gap-1"><MapPin size={14} weight="duotone" /> {league.location}</div>
                <div className="flex items-center gap-1"><Users size={14} weight="duotone" /> {league.member_count} players</div>
                <div className="flex items-center gap-1 font-mono-data text-xs"><Coins size={14} weight="duotone" /> ACE POOL <span className="text-[#F5C542]">${(league.ace_pool || 0).toFixed(0)}</span></div>
                {league.my_bag_tag && <div className="font-mono-data text-xs">MY BAG TAG <span className="text-[#F5C542]">#{league.my_bag_tag}</span></div>}
              </div>
              {league.description && <p className="mt-3 text-sm text-zinc-400 max-w-2xl">{league.description}</p>}
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
        <div className="flex gap-1 mb-6 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.key}
              data-testid={`tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-lg text-sm flex items-center gap-2 flex-shrink-0 transition-colors ${tab === t.key ? "bg-[#F5C542] text-black font-bold" : "bg-white/5 text-zinc-300 hover:bg-white/10"}`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {tab === "rounds" && (
          <div className="space-y-4" data-testid="rounds-tab">
            {league.is_director && (
              <div className="flex justify-end">
                <button
                  data-testid="new-round-btn"
                  onClick={() => setShowNewRound(true)}
                  className="btn-primary flex items-center gap-2"
                >
                  <Plus size={16} weight="bold" /> New Round
                </button>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {rounds.map((r) => (
                <div key={r.id} className="card-surface p-5" data-testid={`round-card-${r.id}`}>
                  <div className="flex items-start justify-between mb-2">
                    <div className="font-display text-lg">{r.name}</div>
                    <div className={`text-[10px] font-mono-data px-2 py-1 rounded-md ${
                      r.status === "completed" ? "chip-green" : r.status === "active" ? "chip-orange" : "bg-zinc-800/60 text-zinc-400 border border-gray-100"
                    }`}>{r.status.toUpperCase()}</div>
                  </div>
                  <div className="text-xs text-zinc-500 mb-4">{new Date(r.date).toLocaleDateString()} · {r.holes} holes</div>
                  <div className="flex gap-2 flex-wrap">
                    <button
                      data-testid={`round-open-${r.id}`}
                      onClick={() => navigate(`/rounds/${r.id}`)}
                      className="text-xs px-3 py-1.5 rounded-full border border-white/15 hover:bg-white/5"
                    >Open Scorecard</button>
                    {league.is_director && r.status === "scheduled" && (
                      <button data-testid={`round-start-${r.id}`} onClick={() => startRound(r.id)} className="text-xs px-3 py-1.5 rounded-full chip-orange flex items-center gap-1">
                        <PlayCircle size={12} weight="fill" /> Start
                      </button>
                    )}
                    {league.is_director && r.status === "active" && (
                      <button data-testid={`round-complete-${r.id}`} onClick={() => completeRound(r.id)} className="text-xs px-3 py-1.5 rounded-full chip-green flex items-center gap-1">
                        <CheckCircle size={12} weight="fill" /> Finalize
                      </button>
                    )}
                    {league.is_director && r.status !== "completed" && (
                      <button
                        data-testid={`round-qr-btn-${r.id}`}
                        onClick={() => setQrRoundId(qrRoundId === r.id ? null : r.id)}
                        className="text-xs px-3 py-1.5 rounded-full border border-slate-300 text-slate-700 hover:bg-slate-100 flex items-center gap-1"
                        title="Show a QR code for players to self-enroll on this round"
                      >
                        <QrCode size={12} weight="bold" /> {qrRoundId === r.id ? "Hide QR" : "QR check-in"}
                      </button>
                    )}
                  </div>
                  {qrRoundId === r.id && (
                    <div className="mt-4" data-testid={`round-qr-wrapper-${r.id}`}>
                      <RoundQRPanel roundId={r.id} roundName={r.name} />
                    </div>
                  )}
                </div>
              ))}
            </div>
            {rounds.length === 0 && (
              <div className="text-zinc-500 text-sm text-center py-8" data-testid="rounds-empty-state">
                No rounds scheduled yet
                {league.is_director && (
                  <div className="mt-3">
                    <button
                      data-testid="rounds-empty-create-btn"
                      onClick={() => setShowNewRound(true)}
                      className="btn-primary text-xs"
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
            members={members}
            isDirector={league.is_director}
            format={league.format}
          />
        )}
        {tab === "ledger" && <LedgerTab leagueId={leagueId} isDirector={league.is_director} />}
        {tab === "clubhouse" && <ClubhouseTab leagueId={leagueId} isDirector={league.is_director} currentUser={user} />}
        {tab === "compliance" && <ComplianceTab leagueId={leagueId} isDirector={league.is_director} />}

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
