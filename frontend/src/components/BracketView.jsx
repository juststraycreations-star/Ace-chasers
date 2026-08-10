import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Trophy, ArrowRight, Printer } from "@phosphor-icons/react";
import SeedManagementPanel from "@/components/SeedManagementPanel";
import BracketPrintOverlay from "@/components/BracketPrintOverlay";
import { useWebSocket } from "@/lib/ws";

/**
 * BracketView — single-elimination visual for "Match Play" leagues.
 * Directors can seed from the current member list and report match
 * results. Winners auto-advance to the linked next-tier slot.
 */
export default function BracketView({ leagueId, leagueName, members, isDirector, format }) {
  const [bracket, setBracket] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reporting, setReporting] = useState(null); // match_id in-flight
  const [seedOverride, setSeedOverride] = useState(false);
  const [printOpen, setPrintOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/leagues/${leagueId}/bracket`);
      setBracket(data);
    } catch {
      setBracket(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [leagueId]);

  // Live toast on any `bracket_advance` broadcast fired by scorecard
  // finalize or director match-report. We subscribe on the LEAGUE
  // channel because bracket state is league-scoped and directors watch
  // this tab across many concurrent rounds.
  useWebSocket(`/api/ws/leagues/${leagueId}`, (msg) => {
    if (!msg) return;
    if (msg.type === "bracket_advance") {
      const win = msg.winner_name || "Winner";
      if (msg.is_final) {
        toast.success(`🏆 ${win} · Bracket Champion!`, {
          description: "Final match resolved — season crown claimed.",
          duration: 8000,
        });
      } else {
        toast.success(`${win} advances`, {
          description: `Winner promoted to ${msg.next_tier_label || "the next tier"}`,
          duration: 5000,
        });
      }
      // Live-refresh the bracket render so viewers see the pin move.
      load();
    } else if (msg.type === "bracket_tie") {
      toast.warning("Match Play tie · director override required", {
        description: "Both finalists tied — sudden-death playoff needed.",
        duration: 6000,
      });
    }
  }, format === "Match Play");

  if (format !== "Match Play") return null;
  if (loading) return null;

  const reset = async () => {
    if (!window.confirm("Wipe the current bracket?")) return;
    try {
      await api.delete(`/leagues/${leagueId}/bracket`);
      toast.success("Bracket cleared");
      await load();
    } catch {
      toast.error("Failed to clear");
    }
  };

  const report = async (match, winnerId) => {
    if (reporting) return;
    setReporting(match.id);
    try {
      await api.post(`/bracket/matches/${match.id}/report`, { winner_id: winnerId });
      toast.success("Result recorded · winner advanced");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Report failed");
    } finally {
      setReporting(null);
    }
  };

  const memberById = Object.fromEntries((members || []).map((m) => [m.id, m]));
  const nameFor = (id) => (id ? memberById[id]?.name || "Player" : "BYE");

  if (!bracket) {
    if (seedOverride) {
      return (
        <SeedManagementPanel
          leagueId={leagueId}
          members={members}
          onSeeded={async () => { setSeedOverride(false); await load(); }}
          onCancel={() => setSeedOverride(false)}
        />
      );
    }
    return (
      <section
        className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm text-center"
        data-testid="bracket-empty"
      >
        <Trophy size={28} weight="duotone" className="text-amber-600 mx-auto mb-2" />
        <div className="font-display text-lg text-slate-900">No bracket seeded</div>
        <div className="text-sm text-slate-600 mt-1">
          Match Play leagues use a single-elimination bracket. Order your players, lock the fixed seeds, and generate.
        </div>
        {isDirector && (
          <button
            type="button"
            onClick={() => setSeedOverride(true)}
            data-testid="bracket-seed-btn"
            className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 rounded-full px-4 py-2"
          >
            Open seed manager
          </button>
        )}
      </section>
    );
  }

  return (
    <section
      className="bg-white border border-slate-200 rounded-2xl p-4 sm:p-6 shadow-sm"
      data-testid="bracket-view"
    >
      {seedOverride && (
        <div className="mb-4" data-testid="bracket-seed-override">
          <SeedManagementPanel
            leagueId={leagueId}
            members={members}
            onSeeded={async () => { setSeedOverride(false); await load(); }}
            onCancel={() => setSeedOverride(false)}
          />
        </div>
      )}
      <div className="flex items-center gap-2 mb-4">
        <Trophy size={22} weight="duotone" className="text-amber-600" />
        <div className="font-display text-xl text-slate-900">Match Play bracket</div>
        {isDirector && (
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => setPrintOpen(true)}
              data-testid="bracket-print-btn"
              className="text-xs font-semibold text-slate-700 border border-slate-200 rounded-full px-3 py-1.5 hover:bg-slate-50 inline-flex items-center gap-1.5"
              title="Print or save as PDF — portrait letter"
            >
              <Printer size={12} weight="duotone" /> Print
            </button>
            <button
              type="button"
              onClick={() => setSeedOverride(true)}
              data-testid="bracket-reseed-btn"
              className="text-xs font-semibold text-slate-700 border border-slate-200 rounded-full px-3 py-1.5 hover:bg-slate-50"
            >
              Re-seed
            </button>
            <button
              type="button"
              onClick={reset}
              data-testid="bracket-reset-btn"
              className="text-xs font-semibold text-red-600 border border-red-200 rounded-full px-3 py-1.5 hover:bg-red-50"
            >
              Reset
            </button>
          </div>
        )}
      </div>

      <div className="flex gap-4 overflow-x-auto pb-2">
        {bracket.tiers.map((tier, tIdx) => (
          <div
            key={tIdx}
            className="min-w-[240px] flex flex-col gap-3"
            data-testid={`bracket-tier-${tIdx}`}
          >
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500 pb-1 border-b border-slate-200">
              {tIdx === bracket.tiers.length - 1 ? "Final" : `Tier ${tIdx + 1}`}
            </div>
            {tier.map((m) => {
              const done = !!m.winner_id;
              return (
                <div
                  key={m.id}
                  className={`rounded-lg border p-3 ${done ? "border-emerald-300 bg-emerald-50/50" : "border-slate-200 bg-white"}`}
                  data-testid={`bracket-match-${m.id}`}
                >
                  {[["a", m.a_member_id], ["b", m.b_member_id]].map(([slot, id]) => {
                    const isWinner = done && m.winner_id === id;
                    return (
                      <div
                        key={slot}
                        className={`flex items-center justify-between py-1.5 ${slot === "a" ? "border-b border-slate-100" : ""}`}
                      >
                        <div className={`text-sm truncate ${isWinner ? "font-bold text-emerald-800" : "text-slate-800"}`}>
                          {nameFor(id)}
                        </div>
                        {isDirector && !done && id && (
                          <button
                            type="button"
                            onClick={() => report(m, id)}
                            disabled={reporting === m.id}
                            data-testid={`bracket-report-${m.id}-${slot}`}
                            className="text-[10px] font-semibold text-amber-700 hover:text-amber-900 disabled:opacity-40 inline-flex items-center gap-0.5"
                          >
                            Wins <ArrowRight size={10} />
                          </button>
                        )}
                        {isWinner && (
                          <span className="text-[10px] font-mono-data text-emerald-700 uppercase tracking-wider">Winner</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {printOpen && (
        <BracketPrintOverlay
          bracket={bracket}
          leagueName={leagueName}
          memberMap={memberById}
          onClose={() => setPrintOpen(false)}
        />
      )}
    </section>
  );
}
