import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { CaretLeft, TrendUp, Trophy } from "@phosphor-icons/react";

export default function PlayerProfile() {
  const { leagueId, memberId } = useParams();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/players/${memberId}`);
        setProfile(data);
      } catch {}
    })();
  }, [leagueId, memberId]);

  if (!profile) {
    return (
      <div className="min-h-screen bg-[#09090B]">
        <AppHeader />
        <div className="max-w-4xl mx-auto p-10 text-zinc-500 font-mono-data text-xs">LOADING…</div>
      </div>
    );
  }

  const { member, handicap, player_rating, history } = profile;

  const chartData = history.map((h, i) => ({
    idx: i + 1,
    name: h.round_name,
    total: h.total,
    diff: h.total - h.course_rating,
    rating: (h.course_rating - h.total) * 10 + 900,
  }));
  const bestRound = history.reduce((best, h) => (!best || h.plus_minus < best.plus_minus ? h : best), null);

  return (
    <div className="min-h-screen bg-[#09090B]" data-testid="player-profile-page">
      <AppHeader />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <button data-testid="back-to-league-btn" onClick={() => navigate(`/leagues/${leagueId}`)} className="text-zinc-400 hover:text-white flex items-center gap-1 text-sm mb-6">
          <CaretLeft size={16} /> Back to League
        </button>

        <div className="card-surface p-8">
          <div className="flex items-start gap-6 flex-wrap">
            {member.picture ? (
              <img src={member.picture} alt="" className="w-24 h-24 rounded-2xl object-cover" />
            ) : (
              <div className="w-24 h-24 rounded-2xl bg-zinc-800 flex items-center justify-center text-3xl font-display">
                {member.name?.charAt(0)}
              </div>
            )}
            <div className="flex-1 min-w-[200px]">
              <div className="font-mono-data text-xs text-zinc-500 mb-1">PLAYER PROFILE</div>
              <h1 className="font-display text-4xl tracking-tighter">{member.name}</h1>
              <div className="mt-2 flex flex-wrap gap-2">
                <div className="chip-orange px-2 py-1 rounded-md text-[10px] font-mono-data">BAG TAG #{member.bag_tag}</div>
                {member.role === "director" && <div className="chip-green px-2 py-1 rounded-md text-[10px] font-mono-data">DIRECTOR</div>}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 sm:min-w-[360px]">
              <div className="text-center">
                <div className="font-mono-data text-[10px] text-zinc-500 mb-1">PLAYER RATING</div>
                <div className="font-mega text-3xl text-[#FF9E00]" data-testid="profile-rating">{player_rating || "—"}</div>
              </div>
              <div className="text-center">
                <div className="font-mono-data text-[10px] text-zinc-500 mb-1">HANDICAP</div>
                <div className="font-mega text-3xl" data-testid="profile-handicap">
                  {handicap > 0 ? `+${handicap}` : handicap || "—"}
                </div>
              </div>
              <div className="text-center">
                <div className="font-mono-data text-[10px] text-zinc-500 mb-1">SEASON PTS</div>
                <div className="font-mega text-3xl">{member.total_points || 0}</div>
              </div>
            </div>
          </div>
        </div>

        {chartData.length > 0 && (
          <div className="card-surface p-6 mt-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-mono-data text-xs text-zinc-500 mb-1">TRENDS</div>
                <h3 className="font-display text-xl flex items-center gap-2"><TrendUp size={18} weight="fill" className="text-[#FF9E00]" /> Round-by-Round</h3>
              </div>
            </div>
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <XAxis dataKey="idx" stroke="#71717a" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#71717a" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ background: "#0f0f11", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: "#a1a1aa" }}
                    formatter={(value, name) => [value, name === "diff" ? "vs rating" : name]}
                  />
                  <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="diff" stroke="#FF5C00" strokeWidth={2.5} dot={{ r: 3, fill: "#FF9E00" }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="text-[10px] font-mono-data text-zinc-500 mt-2">STROKES VS COURSE RATING · LOWER IS BETTER</div>
          </div>
        )}

        <div className="card-surface p-6 mt-6" data-testid="profile-history-table">
          <div className="font-mono-data text-xs text-zinc-500 mb-1">ROUND HISTORY</div>
          <h3 className="font-display text-xl mb-4 flex items-center gap-2"><Trophy weight="fill" className="text-[#FF9E00]" size={18} /> {history.length} Rounds Played</h3>
          {history.length === 0 ? (
            <div className="text-zinc-500 text-sm">No completed rounds yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="ledger-grid">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Round</th>
                    <th style={{ textAlign: "right" }}>Total</th>
                    <th style={{ textAlign: "right" }}>Rating</th>
                    <th style={{ textAlign: "right" }}>vs Rating</th>
                    <th style={{ textAlign: "right" }}>HCP</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h, i) => {
                    const diff = h.total - h.course_rating;
                    const isBest = bestRound && bestRound.round_id === h.round_id;
                    return (
                      <tr key={h.round_id + i} className={isBest ? "bg-[#FF5C00]/5" : ""}>
                        <td className="text-zinc-500">{h.date ? new Date(h.date).toLocaleDateString() : "—"}</td>
                        <td className="font-sans normal-case tracking-normal">{h.round_name || "Round"}{isBest && <span className="ml-2 chip-orange px-1.5 py-0.5 rounded text-[9px]">BEST</span>}</td>
                        <td style={{ textAlign: "right" }}>{h.total}</td>
                        <td style={{ textAlign: "right" }} className="text-zinc-500">{h.course_rating}</td>
                        <td style={{ textAlign: "right" }} className={diff < 0 ? "text-emerald-400" : diff > 0 ? "text-red-400" : "text-zinc-300"}>
                          {diff > 0 ? `+${diff}` : diff}
                        </td>
                        <td style={{ textAlign: "right" }}>{h.handicap_at_round > 0 ? `+${h.handicap_at_round}` : h.handicap_at_round}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
