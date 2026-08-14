import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Trophy, UsersThree, ShareNetwork } from "@phosphor-icons/react";
import { toast } from "sonner";
import { renderDivisionCards, downloadBlob } from "@/lib/shareCard";

/**
 * FormatLeaderboardPanel — format-aware leaderboard shown on active and
 * completed rounds. Consumes `GET /api/rounds/{id}/leaderboard`.
 *
 * Multi-division share (Iteration 54):
 *   For singles-format rounds where members span 2+ divisions, a
 *   director-only "Division cards" button renders one 1080×1350 PNG per
 *   division and triggers a download per card. Powered by
 *   `renderDivisionCards` in /lib/shareCard.js.
 *
 *   Team formats (best-disc / team-sum) don't have per-player divisions,
 *   so the button is hidden in those modes to keep the UI honest.
 */
export default function FormatLeaderboardPanel({
  roundId,
  roundStatus,
  // Optional context — enables the multi-division share button when set.
  isDirector = false,
  leagueName = "",
  roundName = "",
  acePool = 0,
}) {
  const [state, setState] = useState({ loading: true, data: null });
  const [sharing, setSharing] = useState(false);

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

  const divisionGroups = useMemo(() => {
    if (state.data?.mode !== "singles") return [];
    const rows = state.data?.rows || [];
    const map = new Map();
    for (const r of rows) {
      // Skip rows without a real score — projected cards shouldn't
      // pollute the shareable graphic.
      if (!r.total || r.total <= 0) continue;
      const key = r.division || "Open";
      if (!map.has(key)) map.set(key, []);
      map.get(key).push({
        name: r.name,
        total: r.total,
        plusMinus: r.plus_minus || 0,
      });
    }
    return Array.from(map.entries())
      .map(([divisionLabel, leaders]) => ({
        divisionLabel,
        leaders: leaders.slice(0, 5),
      }))
      .sort((a, b) => a.divisionLabel.localeCompare(b.divisionLabel));
  }, [state.data]);

  const canShareDivisions =
    isDirector && divisionGroups.length > 1;

  const downloadDivisionCards = async () => {
    if (sharing) return;
    setSharing(true);
    try {
      const cards = await renderDivisionCards({
        roundName,
        leagueName,
        divisions: divisionGroups,
        acePool,
      });
      let count = 0;
      const safeR = (roundName || "round").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      for (const { divisionLabel, blob } of cards) {
        if (!blob) continue;
        const safeD = divisionLabel.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
        downloadBlob(blob, `ace-chasers-${safeR}-${safeD}.png`);
        count += 1;
      }
      toast.success(`Downloaded ${count} division card${count === 1 ? "" : "s"}`);
    } catch {
      toast.error("Division cards failed");
    } finally {
      setSharing(false);
    }
  };

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
        <div className="flex-1 min-w-0">
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-emerald-700">
            {data.format} · leaderboard
          </div>
          <div className="font-semibold text-sm text-slate-900">{modeLabel}</div>
        </div>
        {canShareDivisions && (
          <button
            type="button"
            onClick={downloadDivisionCards}
            disabled={sharing}
            data-testid="leaderboard-share-divisions-btn"
            title={`One leaderboard PNG per division · ${divisionGroups.length} active`}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-full px-3 py-1.5 disabled:opacity-40 shadow-sm"
          >
            <ShareNetwork size={12} weight="duotone" />
            {sharing ? "…" : `Division cards · ${divisionGroups.length}`}
          </button>
        )}
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
                {row.division && !isTeam && (
                  <span
                    data-testid={`leaderboard-row-${i + 1}-division`}
                    className="hidden sm:inline-block font-mono-data text-[9px] uppercase tracking-widest text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-1.5 py-0.5"
                  >
                    {row.division}
                  </span>
                )}
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
