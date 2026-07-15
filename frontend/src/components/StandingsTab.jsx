import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api, { API } from "../lib/api";
import BagTagMatrix from "./BagTagMatrix";
import { Trophy, TrendUp, DownloadSimple } from "@phosphor-icons/react";

export default function StandingsTab({ leagueId }) {
  const [standings, setStandings] = useState([]);
  const [handicaps, setHandicaps] = useState([]);
  const [members, setMembers] = useState([]);
  const navigate = useNavigate();

  const load = async () => {
    const [s, h, m] = await Promise.all([
      api.get(`/leagues/${leagueId}/standings`),
      api.get(`/leagues/${leagueId}/handicaps`),
      api.get(`/leagues/${leagueId}/members`),
    ]);
    setStandings(s.data);
    setHandicaps(h.data);
    setMembers(m.data);
  };

  useEffect(() => { load(); const t = setInterval(load, 12000); return () => clearInterval(t); }, [leagueId]);

  const hmap = Object.fromEntries(handicaps.map((h) => [h.member_id, h]));

  const exportCsv = () => {
    const token = localStorage.getItem("session_token");
    const url = `${API}/leagues/${leagueId}/standings.csv?auth=${encodeURIComponent(token)}`;
    window.open(url, "_blank");
  };

  return (
    <div className="space-y-8" data-testid="standings-tab">
      <BagTagMatrix members={members} />

      <div className="card-surface p-6 sm:p-8">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-1">LEADERBOARD</div>
            <h3 className="font-display text-2xl flex items-center gap-2">
              <Trophy weight="fill" className="text-[#FF9E00]" size={22} /> Season Standings
            </h3>
          </div>
          <button
            data-testid="standings-export-btn"
            onClick={exportCsv}
            className="text-xs px-3 py-1.5 rounded-full border border-white/15 text-zinc-300 hover:bg-white/5 flex items-center gap-1.5"
          >
            <DownloadSimple size={13} weight="bold" /> Export CSV
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="ledger-grid" data-testid="standings-table">
            <thead>
              <tr>
                <th style={{ width: "60px" }}>Rank</th>
                <th>Player</th>
                <th style={{ width: "80px" }}>Division</th>
                <th style={{ textAlign: "right" }}>Points</th>
                <th style={{ textAlign: "right" }}>Rounds</th>
                <th style={{ textAlign: "right" }}>Rating</th>
                <th style={{ textAlign: "right" }}>Handicap</th>
                <th style={{ textAlign: "right" }}>Bag Tag</th>
              </tr>
            </thead>
            <tbody>
              {standings.map((p, i) => {
                const mem = members.find((m) => m.id === p.member_id);
                return (
                <tr
                  key={p.member_id}
                  data-testid={`standings-row-${i}`}
                  onClick={() => navigate(`/leagues/${leagueId}/players/${p.member_id}`)}
                  className="cursor-pointer hover:bg-white/[0.03]"
                >
                  <td>
                    <span className={`font-mega text-xl ${i === 0 ? "text-[#FF9E00]" : "text-zinc-300"}`}>
                      {String(i + 1).padStart(2, "0")}
                    </span>
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      {p.picture ? (
                        <img src={p.picture} alt="" className="w-7 h-7 rounded-full" />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-[10px]">
                          {p.name?.charAt(0)}
                        </div>
                      )}
                      <span className="font-medium text-zinc-100 font-sans normal-case tracking-normal">{p.name}</span>
                    </div>
                  </td>
                  <td>
                    <span className="chip-orange px-2 py-0.5 rounded text-[10px] font-mono-data" data-testid={`standings-division-${i}`}>{mem?.division || "Open"}</span>
                  </td>
                  <td style={{ textAlign: "right" }} className="text-[#FF9E00]">{p.total_points}</td>
                  <td style={{ textAlign: "right" }}>{p.rounds_played}</td>
                  <td style={{ textAlign: "right" }} className="font-medium">
                    {hmap[p.member_id]?.player_rating ? hmap[p.member_id].player_rating : "—"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {hmap[p.member_id] ? (hmap[p.member_id].handicap > 0 ? `+${hmap[p.member_id].handicap}` : hmap[p.member_id].handicap) : "—"}
                  </td>
                  <td style={{ textAlign: "right" }} className="text-zinc-300">{p.bag_tag}</td>
                </tr>
              );})}
            </tbody>
          </table>
        </div>

        <div className="mt-6 text-xs text-zinc-500 flex items-center gap-2">
          <TrendUp size={14} /> Rating baseline 900 · +10 pts per stroke under course rating (avg of last 5 rounds).
        </div>
      </div>
    </div>
  );
}
