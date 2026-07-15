import { useEffect, useState } from "react";
import api from "@/lib/api";
import BagTagMatrix from "./BagTagMatrix";
import { Trophy, TrendUp } from "@phosphor-icons/react";

export default function StandingsTab({ leagueId }) {
  const [standings, setStandings] = useState([]);
  const [handicaps, setHandicaps] = useState([]);
  const [members, setMembers] = useState([]);

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

  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [leagueId]);

  const hmap = Object.fromEntries(handicaps.map((h) => [h.member_id, h]));

  return (
    <div className="space-y-8" data-testid="standings-tab">
      <BagTagMatrix members={members} />

      <div className="card-surface p-6 sm:p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-1">LEADERBOARD</div>
            <h3 className="font-display text-2xl flex items-center gap-2">
              <Trophy weight="fill" className="text-[#FF9E00]" size={22} /> Season Standings
            </h3>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="ledger-grid" data-testid="standings-table">
            <thead>
              <tr>
                <th style={{ width: "60px" }}>Rank</th>
                <th>Player</th>
                <th style={{ textAlign: "right" }}>Points</th>
                <th style={{ textAlign: "right" }}>Rounds</th>
                <th style={{ textAlign: "right" }}>Handicap</th>
                <th style={{ textAlign: "right" }}>Bag Tag</th>
              </tr>
            </thead>
            <tbody>
              {standings.map((p, i) => (
                <tr key={p.member_id} data-testid={`standings-row-${i}`}>
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
                  <td style={{ textAlign: "right" }} className="text-[#FF9E00]">{p.total_points}</td>
                  <td style={{ textAlign: "right" }}>{p.rounds_played}</td>
                  <td style={{ textAlign: "right" }}>
                    {hmap[p.member_id] ? (hmap[p.member_id].handicap > 0 ? `+${hmap[p.member_id].handicap}` : hmap[p.member_id].handicap) : "—"}
                  </td>
                  <td style={{ textAlign: "right" }} className="text-zinc-300">{p.bag_tag}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-6 text-xs text-zinc-500 flex items-center gap-2">
          <TrendUp size={14} /> Handicap = rolling avg of the last 5 rounds (plus/minus vs par).
        </div>
      </div>
    </div>
  );
}
