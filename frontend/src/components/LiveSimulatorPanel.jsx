import { useMemo, useEffect, useState } from "react";
import api from "@/lib/api";
import { ChartLineUp, MoneyWavy, Tag, Info, ShareNetwork } from "@phosphor-icons/react";
import { toast } from "sonner";
import { renderShareCard, renderDivisionCards, downloadBlob } from "@/lib/shareCard";

/**
 * LiveSimulatorPanel — director-only "pre-finalization" preview shown
 * while `round.status === "active"`.
 *
 * Computes, purely client-side from the live scorecards stream:
 *   1. Projected payout distribution using the 70/20/10 rule:
 *        70% → 1st, 20% → 2nd, 10% → 3rd (of the round's cash pool)
 *   2. Projected bag-tag re-shuffle: whoever's leading takes tag #1,
 *      runner-up tag #2, and so on — with the current holder's old tag
 *      shown in strike-through so directors can see the delta before
 *      it's committed at finalize time.
 *
 * Zero writes. Zero WebSockets of its own — it re-renders every time
 * the parent's `scorecards` prop changes (which already fires on every
 * WebSocket `score_update`).
 */
export default function LiveSimulatorPanel({
  leagueId,
  round,
  scorecards,
  memberMap,
  isDirector,
}) {
  const [pool, setPool] = useState(0);
  const [league, setLeague] = useState(null);
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let dead = false;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}`);
        if (!dead) setLeague(data);
      } catch { /* silent */ }
    })();
    return () => { dead = true; };
  }, [leagueId]);

  // Pull the round's cash pool from the ledger. Falls back to 0 so the
  // panel still renders when no entry fees have been collected yet.
  useEffect(() => {
    if (!leagueId || !round?.id) return;
    let dead = false;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/ledger`, {
          params: { round_id: round.id },
        });
        if (dead) return;
        const total = (data || [])
          .filter((e) => (e.kind || "").toLowerCase().includes("fee"))
          .reduce((a, b) => a + (b.amount || 0), 0);
        setPool(total);
      } catch {
        // Ledger optional — swallow.
      }
    })();
    return () => {
      dead = true;
    };
  }, [leagueId, round?.id]);

  const standings = useMemo(() => {
    const rows = (scorecards || []).map((sc) => {
      const m = memberMap?.[sc.member_id];
      return {
        scorecardId: sc.id,
        memberId: sc.member_id,
        name: m?.name || "Player",
        division: m?.division || "Open",
        oldBagTag: m?.bag_tag ?? null,
        total: sc.total || 0,
        plusMinus: sc.plus_minus || 0,
        holesPlayed: (sc.scores || []).filter((s) => s > 0).length,
      };
    });
    // Sort: fewest strokes first, then most holes played (tie-break).
    rows.sort((a, b) => {
      if (a.total !== b.total) return a.total - b.total;
      return b.holesPlayed - a.holesPlayed;
    });
    return rows;
  }, [scorecards, memberMap]);

  const divisionGroups = useMemo(() => {
    const map = new Map();
    for (const r of standings) {
      const key = r.division || "Open";
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(r);
    }
    return Array.from(map.entries())
      .map(([divisionLabel, leaders]) => ({ divisionLabel, leaders: leaders.slice(0, 5) }))
      .sort((a, b) => a.divisionLabel.localeCompare(b.divisionLabel));
  }, [standings]);

  const payoutSplit = useMemo(() => {
    if (!pool) return [];
    return [
      { rank: 1, pct: 0.7, cash: Math.round(pool * 0.7) },
      { rank: 2, pct: 0.2, cash: Math.round(pool * 0.2) },
      { rank: 3, pct: 0.1, cash: Math.round(pool * 0.1) },
    ];
  }, [pool]);

  if (!isDirector || !round || round.status !== "active") return null;

  return (
    <section
      className="bg-slate-900 text-slate-100 rounded-2xl p-5 sm:p-6 mb-6 border border-slate-800"
      data-testid="live-simulator-panel"
      aria-label="Pre-finalization simulator"
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
          <ChartLineUp size={18} weight="duotone" />
        </div>
        <div className="flex-1">
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-emerald-400">
            Pre-finalization simulator · live
          </div>
          <div className="font-display text-lg text-white">
            Projected payouts & bag-tag reshuffle
          </div>
        </div>
        <div
          className="hidden sm:flex items-center gap-1 text-[10px] font-mono-data text-slate-400"
          title="This panel is read-only. Nothing is written until you finalize the round."
        >
          <Info size={12} /> read-only preview
        </div>
        <button
          type="button"
          onClick={async () => {
            if (sharing) return;
            setSharing(true);
            try {
              const common = {
                roundName: round?.name,
                leagueName: league?.name,
                leaders: standings.slice(0, 5).map((r) => ({
                  name: r.name,
                  total: r.total,
                  plusMinus: r.plusMinus,
                })),
                payouts: payoutSplit,
                acePool: league?.ace_pool || 0,
                pool,
              };
              const blob = await renderShareCard({ ...common, template: "winner" });
              if (!blob) throw new Error("no blob");
              const safe = (round?.name || "round").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
              downloadBlob(blob, `ace-chasers-${safe}-winner.png`);
              toast.success("Winner's Circle card downloaded");
            } catch {
              toast.error("Share card failed");
            } finally {
              setSharing(false);
            }
          }}
          disabled={sharing}
          data-testid="simulator-share-winner-btn"
          className="ml-2 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-900 bg-amber-400 hover:bg-amber-500 rounded-full px-3 py-1.5 disabled:opacity-40"
        >
          <ShareNetwork size={12} weight="duotone" />
          {sharing ? "…" : "Winner card"}
        </button>
        <button
          type="button"
          onClick={async () => {
            if (sharing) return;
            setSharing(true);
            try {
              const blob = await renderShareCard({
                roundName: round?.name,
                leagueName: league?.name,
                leaders: standings.slice(0, 5).map((r) => ({
                  name: r.name,
                  total: r.total,
                  plusMinus: r.plusMinus,
                })),
                payouts: payoutSplit,
                acePool: league?.ace_pool || 0,
                pool,
                template: "leaderboard",
              });
              if (!blob) throw new Error("no blob");
              const safe = (round?.name || "round").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
              downloadBlob(blob, `ace-chasers-${safe}-leaderboard.png`);
              toast.success("Leaderboard card downloaded");
            } catch {
              toast.error("Share card failed");
            } finally {
              setSharing(false);
            }
          }}
          disabled={sharing}
          data-testid="simulator-share-leaderboard-btn"
          className="ml-2 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-100 border border-slate-500 hover:border-slate-300 rounded-full px-3 py-1.5 disabled:opacity-40"
        >
          <ShareNetwork size={12} weight="duotone" />
          Leaderboard
        </button>
        {divisionGroups.length > 1 && (
          <button
            type="button"
            onClick={async () => {
              if (sharing) return;
              setSharing(true);
              try {
                const cards = await renderDivisionCards({
                  roundName: round?.name,
                  leagueName: league?.name,
                  divisions: divisionGroups.map((d) => ({
                    divisionLabel: d.divisionLabel,
                    leaders: d.leaders.map((r) => ({
                      name: r.name,
                      total: r.total,
                      plusMinus: r.plusMinus,
                    })),
                  })),
                  acePool: league?.ace_pool || 0,
                });
                let count = 0;
                for (const { divisionLabel, blob } of cards) {
                  if (!blob) continue;
                  const safeR = (round?.name || "round").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
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
            }}
            disabled={sharing}
            data-testid="simulator-share-divisions-btn"
            className="ml-2 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-900 bg-emerald-400 hover:bg-emerald-500 rounded-full px-3 py-1.5 disabled:opacity-40"
            title={`One leaderboard PNG per division · ${divisionGroups.length} active`}
          >
            <ShareNetwork size={12} weight="duotone" />
            {sharing ? "…" : `Division cards · ${divisionGroups.length}`}
          </button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Payouts */}
        <div
          className="rounded-xl bg-slate-800/50 border border-slate-700 p-4"
          data-testid="simulator-payouts"
        >
          <div className="flex items-center gap-2 mb-3">
            <MoneyWavy size={16} weight="duotone" className="text-amber-400" />
            <div className="font-semibold text-sm">Projected payouts</div>
            <div className="ml-auto text-[10px] font-mono-data text-slate-400">
              POOL ${pool.toFixed(0)} · 70/20/10
            </div>
          </div>
          {pool === 0 ? (
            <div className="text-xs text-slate-400" data-testid="simulator-payouts-empty">
              No entry fees collected yet. Payouts will project once the ledger
              has round fees.
            </div>
          ) : (
            <ol className="space-y-2">
              {payoutSplit.map((slot, i) => {
                const row = standings[i];
                return (
                  <li
                    key={slot.rank}
                    className="flex items-center justify-between gap-3 text-sm"
                    data-testid={`simulator-payout-row-${slot.rank}`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-6 h-6 rounded-md bg-amber-500/10 text-amber-400 font-mono text-[10px] flex items-center justify-center">
                        {slot.rank}
                      </span>
                      <span className="truncate text-slate-100">
                        {row ? row.name : "—"}
                      </span>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-mono-data text-sm text-amber-300">
                        ${slot.cash}
                      </div>
                      <div className="font-mono-data text-[9px] text-slate-500">
                        {Math.round(slot.pct * 100)}%
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>

        {/* Bag tag reshuffle */}
        <div
          className="rounded-xl bg-slate-800/50 border border-slate-700 p-4"
          data-testid="simulator-bagtag"
        >
          <div className="flex items-center gap-2 mb-3">
            <Tag size={16} weight="duotone" className="text-sky-400" />
            <div className="font-semibold text-sm">Projected bag-tag order</div>
          </div>
          {standings.length === 0 ? (
            <div className="text-xs text-slate-400">
              No scores yet — no reshuffle to preview.
            </div>
          ) : (
            <ol className="space-y-1.5">
              {standings.slice(0, 8).map((row, i) => {
                const newTag = i + 1;
                const changed = row.oldBagTag != null && row.oldBagTag !== newTag;
                return (
                  <li
                    key={row.scorecardId}
                    className="flex items-center justify-between text-sm"
                    data-testid={`simulator-bagtag-row-${newTag}`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-6 h-6 rounded-md bg-sky-500/10 text-sky-400 font-mono text-[10px] flex items-center justify-center">
                        {newTag}
                      </span>
                      <span className="truncate text-slate-100">{row.name}</span>
                    </div>
                    <div className="font-mono-data text-[10px] text-slate-400">
                      {row.oldBagTag != null && (
                        <span className={changed ? "line-through text-slate-600 mr-1" : "mr-1"}>
                          #{row.oldBagTag}
                        </span>
                      )}
                      {changed && (
                        <span className="text-emerald-400">→ #{newTag}</span>
                      )}
                      <span className="ml-2 text-slate-500">
                        {row.total} ({row.plusMinus >= 0 ? "+" : ""}
                        {row.plusMinus})
                      </span>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}
