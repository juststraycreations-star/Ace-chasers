import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Trophy, UsersThree } from "@phosphor-icons/react";

/**
 * FormatLeaderboardPanel — format-aware leaderboard shown on active
 * rounds. Consumes `GET /api/rounds/{id}/leaderboard` which returns:
 *   { format, mode: "singles" | "best_disc" | "team_sum", rows: [...] }
 *
 * In "singles" mode each row is one player. In "best_disc" / "team_sum"
 * modes each row is a card/team with the aggregated total and, for
 * best-disc, the per-hole combined scores.
 */
export default function FormatLeaderboardPanel({ roundId, roundStatus }) {
  const [state, setState] = useState({ loading: true, data: null });

  useEffect(() => {
    let cancelled = false;
    const fetchIt = async () => {
      try {
        const { data } = await api.get(`/rounds/${roundId}/leaderboard`);
        if (!cancelled) setState({ loading: false, data });
      } catch {
        if (!cancelled) setState({ loading: false, data: null });
      }
    };
    fetchIt();
    // Live rounds: poll every 10s so team leaderboard tracks progress
    // without needing another WebSocket subscription.
    let t;
    if (roundStatus === "active") {
      t = setInterval(fetchIt, 10000);
    }
    return () => {
      cancelled = true;
      if (t) clearInterval(t);
    };
  }, [roundId, roundStatus]);

  const { loading, data } = state;
  if (loading) return null;
  if (!data || !data.rows || data.rows.length === 0) return null;

  const isTeam = data.mode !== "singles";
  const modeLabel = data.mode === "best_disc" ? "Best-disc team totals"
    : data.mode === "team_sum" ? "Combined team totals"
    : "Player totals";

  return (
    <section
      className="bg-white border border-emerald-100 rounded-2xl shadow-sm p-5 mb-6"
      data-testid="format-leaderboard-panel"
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center">
          {isTeam ? <UsersThree size={18} weight="duotone" /> : <Trophy size={18} weight="duotone" />}
        </div>
        <div>
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-emerald-700">
            {data.format} · leaderboard
          </div>
          <div className="font-semibold text-sm text-slate-900">{modeLabel}</div>
        </div>
      </div>
      <ol className="space-y-1.5">
        {data.rows.slice(0, 8).map((row, i) => {
          const total = row.total || 0;
          const pm = row.plus_minus || 0;
          const name = isTeam
            ? row.team_label + (row.player_names?.length ? ` · ${row.player_names.join(" & ")}` : "")
            : row.name;
          return (
            <li
              key={row.team_id || row.member_id}
              className="flex items-center justify-between gap-3 text-sm py-1"
              data-testid={`leaderboard-row-${i + 1}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="w-6 h-6 rounded-md bg-emerald-100 text-emerald-800 font-mono text-[10px] flex items-center justify-center">
                  {i + 1}
                </span>
                <span className="truncate text-slate-900">{name}</span>
              </div>
              <div className="text-right shrink-0 font-mono-data">
                <span className="text-slate-900 font-semibold">{total}</span>
                <span
                  className={`ml-2 text-xs ${pm < 0 ? "text-emerald-600" : pm > 0 ? "text-slate-500" : "text-slate-400"}`}
                >
                  {pm > 0 ? `+${pm}` : pm}
                </span>
                <span className="ml-2 text-[10px] text-slate-400">
                  · {row.holes_played || 0} played
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
