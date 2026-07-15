import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useWebSocket } from "@/lib/ws";
import { toast } from "sonner";
import { CaretLeft, Minus, Plus, ChatCircleText, Terminal, ArrowsClockwise, UsersThree, Shuffle, Ghost, Target, MoneyWavy } from "@phosphor-icons/react";
import GhostOverlay from "@/components/GhostOverlay";
import CTPLeaderboard from "@/components/CTPLeaderboard";
import DirectorNotesBanner from "@/components/DirectorNotesBanner";
import PayoutDistribution from "@/components/PayoutDistribution";

function scoreClass(strokes, par) {
  if (!strokes) return "";
  const diff = strokes - par;
  if (diff <= -2) return "eagle-plus";
  if (diff === -1) return "birdie";
  if (diff === 1) return "bogey";
  if (diff >= 2) return "double-plus";
  return "filled";
}

export default function RoundScorecard() {
  const { roundId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [members, setMembers] = useState([]);
  const [selectedCardId, setSelectedCardId] = useState(null);
  const [currentHole, setCurrentHole] = useState(1);
  const [proof, setProof] = useState([]);
  const [showProofFor, setShowProofFor] = useState(null);
  const [chat, setChat] = useState([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatText, setChatText] = useState("");
  const [showBuilder, setShowBuilder] = useState(false);
  const [newCard, setNewCard] = useState({ label: "Card A", player_ids: [] });
  const [league, setLeague] = useState(null);
  const [ghostMemberId, setGhostMemberId] = useState(null);
  const [showCTP, setShowCTP] = useState(false);
  const [ctpRefresh, setCtpRefresh] = useState(0);
  const [showPayout, setShowPayout] = useState(false);
  const chatEnd = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/rounds/${roundId}`);
      setData(data);
      if (!selectedCardId && data.cards.length > 0) setSelectedCardId(data.cards[0].id);
      const memb = await api.get(`/leagues/${data.round.league_id}/members`);
      setMembers(memb.data);
      const lg = await api.get(`/leagues/${data.round.league_id}`);
      setLeague(lg.data);
    } catch { toast.error("Failed to load round"); }
  };

  const loadChat = useCallback(async () => {
    if (!selectedCardId) return;
    try {
      const { data } = await api.get(`/rounds/${roundId}/chat`, { params: { card_id: selectedCardId } });
      setChat(data);
    } catch {}
  }, [roundId, selectedCardId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadChat(); }, [loadChat]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chat.length]);

  // WebSocket for realtime updates
  const { connected } = useWebSocket(`/api/ws/rounds/${roundId}`, useCallback((msg) => {
    if (msg.type === "score_update") {
      load();
    } else if (msg.type === "chat") {
      const newMsg = msg.message;
      if (newMsg.card_id === selectedCardId || (!newMsg.card_id && !selectedCardId)) {
        setChat((prev) => (prev.some((m) => m.id === newMsg.id) ? prev : [...prev, newMsg]));
      }
    } else if (msg.type === "cards_updated") {
      load();
    } else if (msg.type === "director_notes") {
      load();
    } else if (msg.type === "ctp_entry" || msg.type === "ctp_deleted") {
      setCtpRefresh((v) => v + 1);
    }
  }, [load, selectedCardId]));

  const round = data?.round;
  const cards = data?.cards || [];
  const scorecards = data?.scorecards || [];
  const activeCard = cards.find((c) => c.id === selectedCardId);
  const cardScorecards = scorecards.filter((sc) => sc.card_id === selectedCardId);
  const memberMap = Object.fromEntries(members.map((m) => [m.id, m]));
  const leagueFormat = league?.format || "Singles";
  const isDirector = !!(league?.is_director);

  const updateScore = async (scorecardId, hole, strokes) => {
    if (strokes < 0) strokes = 0;
    try {
      await api.patch(`/scorecards/${scorecardId}/score`, { hole, strokes });
      await load();
    } catch { toast.error("Failed to save"); }
  };

  const openProof = async (scorecardId) => {
    setShowProofFor(scorecardId);
    try {
      const { data } = await api.get(`/scorecards/${scorecardId}/proof`);
      setProof(data);
    } catch {}
  };

  const sendChat = async () => {
    if (!chatText.trim()) return;
    try {
      await api.post(`/rounds/${roundId}/chat`, { text: chatText, card_id: selectedCardId });
      setChatText("");
      await loadChat();
    } catch { toast.error("Failed to send"); }
  };

  const createCard = async () => {
    if (newCard.player_ids.length === 0) { toast.error("Pick at least 1 player"); return; }
    try {
      await api.post(`/rounds/${roundId}/cards`, { label: newCard.label, player_ids: newCard.player_ids });
      setShowBuilder(false);
      setNewCard({ label: "Card A", player_ids: [] });
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const autoPair = async () => {
    if (!window.confirm("Auto-pair will REPLACE existing cards and scorecards for this round with random pairs. Continue?")) return;
    try {
      await api.post(`/rounds/${roundId}/auto-pair`, {
        member_ids: members.map((m) => m.id),
        card_size: leagueFormat === "Singles" ? 1 : 2,
      });
      toast.success("Cards drawn");
      setSelectedCardId(null);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Auto-pair failed"); }
  };

  if (!round) return <div className="min-h-screen bg-[#1f4d2e] flex items-center justify-center text-zinc-500 font-mono-data text-xs">LOADING…</div>;

  const par = round.par_per_hole[currentHole - 1];

  return (
    <div className="min-h-screen bg-[#1f4d2e] pb-32" data-testid="round-scorecard-page">
      {/* Sticky header */}
      <div className="scorecard-header">
        <div className="max-w-4xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <button data-testid="back-to-league-btn" onClick={() => navigate(`/leagues/${round.league_id}`)} className="text-zinc-400 hover:text-white flex items-center gap-1 text-sm">
              <CaretLeft size={16} /> Back
            </button>
            <div className="text-center">
              <div className="font-mono-data text-[10px] text-zinc-500">HOLE {currentHole} · PAR</div>
              <div className="font-mega text-4xl leading-none text-[#F5C542]">{par}</div>
            </div>
            <div className="text-right">
              <div className="font-mono-data text-[10px] text-zinc-500">ROUND</div>
              <div className="text-sm font-display">{round.name}</div>
            </div>
          </div>

          {/* Hole nav */}
          <div className="mt-3 flex gap-1 overflow-x-auto pb-1">
            {round.par_per_hole.map((p, i) => (
              <button
                key={i}
                data-testid={`hole-nav-${i+1}`}
                onClick={() => setCurrentHole(i + 1)}
                className={`flex-shrink-0 w-9 h-9 rounded-lg text-xs font-bold transition-colors ${currentHole === i + 1 ? "bg-[#F5C542] text-black" : "bg-white/5 text-zinc-400 hover:bg-white/10"}`}
              >{i + 1}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6">
        <DirectorNotesBanner round={round} isDirector={isDirector} onUpdated={load} />

        {/* Card picker */}
        <div className="flex items-center gap-2 mb-6 overflow-x-auto">
          {cards.map((c) => (
            <button
              key={c.id}
              data-testid={`card-tab-${c.id}`}
              onClick={() => setSelectedCardId(c.id)}
              className={`px-4 py-2 rounded-full text-sm flex-shrink-0 border ${selectedCardId === c.id ? "bg-[#F5C542]/15 border-[#F5C542] text-white" : "border-white/10 text-zinc-400"}`}
            >
              {c.label} <span className="text-[10px] font-mono-data ml-1 opacity-70">·{c.player_ids.length}</span>
            </button>
          ))}
          <button data-testid="new-card-btn" onClick={() => setShowBuilder(!showBuilder)} className="px-4 py-2 rounded-full text-sm border border-dashed border-white/15 text-zinc-400 hover:border-white/40 flex items-center gap-1 flex-shrink-0">
            <Plus size={14} weight="bold" /> New Card
          </button>
          {isDirector && (leagueFormat === "Random-Draw Doubles" || leagueFormat === "BYOP" || leagueFormat === "Team") && (
            <button data-testid="auto-pair-btn" onClick={autoPair} className="px-4 py-2 rounded-full text-sm border border-[#F5C542]/40 bg-[#F5C542]/10 text-[#F5C542] hover:bg-[#F5C542]/20 flex items-center gap-1 flex-shrink-0">
              <Shuffle size={14} weight="bold" /> Auto-Pair
            </button>
          )}
          <button data-testid="ctp-toggle-btn" onClick={() => setShowCTP(!showCTP)} className={`px-4 py-2 rounded-full text-sm border flex items-center gap-1 flex-shrink-0 ${showCTP ? "border-[#F5C542]/40 bg-[#F5C542]/10 text-[#F5C542]" : "border-white/10 text-zinc-400 hover:border-white/25"}`}>
            <Target size={14} weight="duotone" /> CTP
          </button>
          <button data-testid="payout-open-btn" onClick={() => setShowPayout(true)} className="px-4 py-2 rounded-full text-sm border border-white/10 text-zinc-400 hover:border-white/25 flex items-center gap-1 flex-shrink-0">
            <MoneyWavy size={14} weight="duotone" /> Payouts
          </button>
        </div>

        {showBuilder && (
          <div className="card-surface p-5 mb-6" data-testid="card-builder">
            <div className="font-display text-lg mb-3 flex items-center gap-2"><UsersThree /> Build a Card</div>
            <input
              data-testid="new-card-label"
              value={newCard.label}
              onChange={(e) => setNewCard({ ...newCard, label: e.target.value })}
              className="w-full h-11 bg-[#2a5f3d] border border-white/10 rounded-md px-3 mb-3"
              placeholder="Card Label"
            />
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
              {members.map((m) => {
                const picked = newCard.player_ids.includes(m.id);
                return (
                  <button
                    key={m.id}
                    data-testid={`pick-member-${m.id}`}
                    onClick={() => setNewCard({ ...newCard, player_ids: picked ? newCard.player_ids.filter((x) => x !== m.id) : [...newCard.player_ids, m.id] })}
                    className={`p-3 rounded-lg border text-left text-sm ${picked ? "border-[#F5C542] bg-[#F5C542]/12" : "border-white/10 bg-[#2a5f3d]"}`}
                  >
                    <div className="text-xs text-zinc-500 font-mono-data">#{m.bag_tag}</div>
                    <div className="font-medium">{m.name}</div>
                  </button>
                );
              })}
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowBuilder(false)} className="text-xs px-3 py-2 text-zinc-400">Cancel</button>
              <button data-testid="save-card-btn" onClick={createCard} className="btn-primary text-xs">Create Card</button>
            </div>
          </div>
        )}

        {!activeCard && (
          <div className="card-surface p-8 text-center text-zinc-500 text-sm">No cards yet. Create one to start scoring.</div>
        )}

        {activeCard && (
          <div className="space-y-3" data-testid="active-card-scoring">
            {/* Ghost selector: player picks another scorecard to overlay */}
            {cardScorecards.length > 0 && (() => {
              const myScorecard = cardScorecards.find((sc) => memberMap[sc.member_id]?.user_id === user?.user_id);
              const otherScs = scorecards.filter((sc) => sc.id !== myScorecard?.id);
              const ghostSc = otherScs.find((sc) => sc.member_id === ghostMemberId);
              const ghostMember = ghostSc ? memberMap[ghostSc.member_id] : null;
              return (
                <div className="card-surface p-3 flex items-center gap-3 flex-wrap" data-testid="ghost-selector">
                  <div className="flex items-center gap-2">
                    <Ghost size={16} weight="duotone" className="text-[#F5C542]" />
                    <span className="font-mono-data text-[10px] text-zinc-500">GHOST</span>
                  </div>
                  <select
                    data-testid="ghost-select"
                    value={ghostMemberId || ""}
                    onChange={(e) => setGhostMemberId(e.target.value || null)}
                    className="h-9 bg-[#2a5f3d] border border-white/10 rounded-md px-2 text-sm min-w-[180px]"
                  >
                    <option value="">None</option>
                    {otherScs.map((sc) => {
                      const mm = memberMap[sc.member_id];
                      return <option key={sc.id} value={sc.member_id}>{mm?.name || "Player"} · {sc.total || 0}</option>;
                    })}
                  </select>
                  {ghostSc && myScorecard && (
                    <div className="text-xs text-zinc-500 font-mono-data">
                      OVERLAY ACTIVE · CURRENT DIFF <span className="text-white">{(myScorecard.total || 0) - (ghostSc.total || 0)}</span>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Ghost overlay */}
            {(() => {
              const myScorecard = cardScorecards.find((sc) => memberMap[sc.member_id]?.user_id === user?.user_id);
              const ghostSc = ghostMemberId ? scorecards.find((sc) => sc.member_id === ghostMemberId) : null;
              const ghostMember = ghostSc ? memberMap[ghostSc.member_id] : null;
              if (!myScorecard || !ghostSc) return null;
              return (
                <GhostOverlay
                  playerScorecard={myScorecard}
                  ghostScorecard={ghostSc}
                  ghostName={ghostMember?.name || "Ghost"}
                  parPerHole={round.par_per_hole}
                  currentHole={currentHole}
                  onClose={() => setGhostMemberId(null)}
                />
              );
            })()}

            {/* CTP widget */}
            {showCTP && (() => {
              const myScorecard = cardScorecards.find((sc) => memberMap[sc.member_id]?.user_id === user?.user_id);
              return (
                <CTPLeaderboard
                  roundId={roundId}
                  currentHole={currentHole}
                  currentMemberId={myScorecard?.member_id}
                  isDirector={isDirector}
                  refresh={ctpRefresh}
                />
              );
            })()}

            {cardScorecards.map((sc) => {
              const m = memberMap[sc.member_id];
              const holeScore = sc.scores[currentHole - 1];
              return (
                <div key={sc.id} className="card-surface p-4" data-testid={`scorecard-row-${sc.id}`}>
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="bag-tag" style={{ width: 44, height: 44, fontSize: 22 }}>{m?.bag_tag ?? "?"}</div>
                      <div className="min-w-0">
                        <div className="font-medium truncate">{m?.name ?? "Player"}</div>
                        <div className="font-mono-data text-[10px] text-zinc-500">
                          TOTAL <span className="text-white">{sc.total}</span> · {sc.plus_minus > 0 ? `+${sc.plus_minus}` : sc.plus_minus} · HCP {sc.handicap_at_round > 0 ? `+${sc.handicap_at_round}` : sc.handicap_at_round}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        data-testid={`score-minus-${sc.id}`}
                        onClick={() => updateScore(sc.id, currentHole, (holeScore || par) - 1)}
                        className="w-11 h-11 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center hover:bg-white/10"
                      ><Minus weight="bold" /></button>
                      <div className={`hole-cell ${scoreClass(holeScore, par)}`} data-testid={`score-cell-${sc.id}`} style={{ width: 56, height: 56 }}>
                        {holeScore || "—"}
                      </div>
                      <button
                        data-testid={`score-plus-${sc.id}`}
                        onClick={() => updateScore(sc.id, currentHole, (holeScore || par) + (holeScore ? 1 : 1))}
                        className="w-11 h-11 rounded-lg bg-[#F5C542]/15 border border-[#F5C542]/40 text-[#F5C542] flex items-center justify-center hover:bg-[#F5C542]/25"
                      ><Plus weight="bold" /></button>
                      <button
                        data-testid={`proof-btn-${sc.id}`}
                        onClick={() => openProof(sc.id)}
                        className="ml-1 text-zinc-500 hover:text-white p-2"
                        title="Proof of Score"
                      ><Terminal size={16} weight="duotone" /></button>
                    </div>
                  </div>
                  {/* Full holes strip */}
                  <div className="mt-3 grid gap-1" style={{ gridTemplateColumns: `repeat(${sc.scores.length}, minmax(0, 1fr))` }}>
                    {sc.scores.map((s, i) => (
                      <div key={i} className={`hole-cell ${scoreClass(s, round.par_per_hole[i])}`} style={{ minHeight: 32, fontSize: 14, minWidth: 0 }}>
                        {s || ""}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Proof modal */}
        {showProofFor && (
          <div className="fixed inset-0 z-40 bg-black/70 flex items-center justify-center p-4" onClick={() => setShowProofFor(null)} data-testid="proof-modal">
            <div className="card-surface max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-mono-data text-xs text-zinc-500">PROOF OF SCORE</div>
                  <div className="font-display text-xl">Audit Log</div>
                </div>
                <button data-testid="close-proof-btn" onClick={() => setShowProofFor(null)} className="text-zinc-500 hover:text-white">×</button>
              </div>
              <div className="terminal">
                {proof.length === 0 && <div>// no edits yet</div>}
                {proof.map((p) => (
                  <div key={p.id}>
                    <span className="ts">[{new Date(p.timestamp).toLocaleTimeString()}]</span> H{p.hole} <span className="val">{p.old_value}→{p.new_value}</span> · {p.edited_by_name}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Round total footer */}
        {activeCard && (
          <div className="mt-8 text-xs text-zinc-500 font-mono-data flex items-center gap-2">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"}`}></span>
            {connected ? "LIVE · WEBSOCKET CONNECTED" : "RECONNECTING…"}
          </div>
        )}

        {showPayout && (
          <PayoutDistribution
            roundId={roundId}
            leagueName={league?.name}
            isDirector={isDirector}
            onClose={() => setShowPayout(false)}
          />
        )}
      </div>

      {/* Chat drawer */}
      {activeCard && (
        <>
          <button
            data-testid="chat-toggle-btn"
            onClick={() => setChatOpen(!chatOpen)}
            className="fixed bottom-6 right-6 z-30 w-14 h-14 rounded-full bg-[#F5C542] text-black shadow-2xl flex items-center justify-center hover:scale-105 transition-transform"
          >
            <ChatCircleText size={22} weight="fill" />
          </button>
          {chatOpen && (
            <div className="fixed bottom-24 right-6 z-30 w-[min(360px,calc(100vw-2rem))] glass rounded-2xl overflow-hidden flex flex-col" style={{ maxHeight: "60vh" }} data-testid="chat-drawer">
              <div className="p-3 border-b border-white/10 flex items-center justify-between">
                <div className="font-display text-sm">Card Chat · {activeCard.label}</div>
                <button onClick={() => setChatOpen(false)} className="text-zinc-500 hover:text-white text-xl leading-none">×</button>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {chat.length === 0 && <div className="text-zinc-500 text-xs text-center py-4">Say hi 👋</div>}
                {chat.map((m) => (
                  <div key={m.id} className={`p-2 rounded-lg text-sm ${m.user_id === user?.user_id ? "bg-[#F5C542]/15 border border-[#F5C542]/25 ml-6" : "bg-white/5 border border-white/8 mr-6"}`} data-testid={`chat-msg-${m.id}`}>
                    <div className="text-[10px] font-mono-data text-zinc-500 mb-0.5">{m.user_name} · {new Date(m.timestamp).toLocaleTimeString()}</div>
                    <div>{m.text}</div>
                  </div>
                ))}
                <div ref={chatEnd} />
              </div>
              <div className="p-2 border-t border-white/10 flex gap-2">
                <input
                  data-testid="chat-input"
                  value={chatText}
                  onChange={(e) => setChatText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendChat()}
                  placeholder="Message + 🥏"
                  className="flex-1 h-10 bg-[#2a5f3d] border border-white/10 rounded-md px-3 text-sm"
                />
                <button data-testid="chat-send-btn" onClick={sendChat} className="btn-primary text-xs px-4">Send</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
