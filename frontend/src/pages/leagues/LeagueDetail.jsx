import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import StandingsTab from "@/components/StandingsTab";
import LedgerTab from "@/components/LedgerTab";
import ClubhouseTab from "@/components/ClubhouseTab";
import ClubhouseAgreementModal from "@/components/ClubhouseAgreementModal";
import { useAuth } from "@/context/AuthContext";
import LeagueLiveNotifier from "@/components/LeagueLiveNotifier";
import { MapPin, Users, Trophy, Coins, ChatCircle, Calendar, Plus, PlayCircle, CheckCircle, QrCode } from "@phosphor-icons/react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";

export default function LeagueDetail() {
  const { leagueId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [league, setLeague] = useState(null);
  const [rounds, setRounds] = useState([]);
  const [members, setMembers] = useState([]);
  const [tab, setTab] = useState("rounds");
  const [showQR, setShowQR] = useState(false);

  const load = async () => {
    try {
      const [lg, rd, mm] = await Promise.all([
        api.get(`/leagues/${leagueId}`),
        api.get(`/leagues/${leagueId}/rounds`).catch(() => ({ data: [] })),
        api.get(`/leagues/${leagueId}/members`).catch(() => ({ data: [] })),
      ]);
      setLeague(lg.data);
      setRounds(rd.data);
      setMembers(mm.data);
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

  if (!league) return (
    <div className="min-h-screen bg-white"><AppHeader /><div className="max-w-7xl mx-auto p-10 text-zinc-500 font-mono-data text-xs">LOADING…</div></div>
  );

  const checkInUrl = `${window.location.origin}/leagues/${leagueId}?join=1`;

  const tabs = [
    { key: "rounds", label: "Rounds", icon: <Calendar size={15} /> },
    { key: "standings", label: "Standings", icon: <Trophy size={15} /> },
    { key: "ledger", label: "Ledger", icon: <Coins size={15} /> },
    { key: "clubhouse", label: "Clubhouse", icon: <ChatCircle size={15} /> },
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
                  </div>
                </div>
              ))}
            </div>
            {rounds.length === 0 && <div className="text-zinc-500 text-sm text-center py-8">No rounds scheduled yet</div>}
          </div>
        )}

        {tab === "standings" && <StandingsTab leagueId={leagueId} />}
        {tab === "ledger" && <LedgerTab leagueId={leagueId} isDirector={league.is_director} />}
        {tab === "clubhouse" && <ClubhouseTab leagueId={leagueId} isDirector={league.is_director} currentUser={user} />}

        {/* Fair Play Agreement modal — covers Announcements-only viewers and
            every other private league surface. Renders once per league until
            the member ticks "I Agree". */}
        {league.is_member && league.my_clubhouse_agreed === false && (
          <ClubhouseAgreementModal
            leagueId={leagueId}
            onAgree={() => setLeague((prev) => prev ? { ...prev, my_clubhouse_agreed: true } : prev)}
          />
        )}
      </main>
    </div>
  );
}
