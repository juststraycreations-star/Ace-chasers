import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { X, Printer, Trophy, Target, Fire } from "@phosphor-icons/react";

/**
 * RoundRecapPoster — printable per-round recap the director can hand
 * out on the tee pad. Renders inline as a print-ready portrait-letter
 * poster and auto-fires `window.print()` on mount.
 *
 * Data is assembled entirely client-side from the existing round + CTP
 * endpoints so no new backend surface is required.
 *
 *   • Top 3 finishers: sorted by NET (total − handicap_at_round). Ties
 *     break on total, then holes played.
 *   • Hot Round: player with the deepest under-par delta (lowest
 *     plus_minus). If nobody was under par, the least-over-par player.
 *   • CTP winners: one row per hole, closest wins.
 */
export default function RoundRecapPoster({
  round,
  league,
  scorecards,
  members,
  onClose,
}) {
  const [ctp, setCtp] = useState({ leaderboard: {}, ctp_holes: [] });

  useEffect(() => {
    if (!round?.id) return;
    let dead = false;
    (async () => {
      try {
        const { data } = await api.get(`/rounds/${round.id}/ctp`);
        if (!dead) setCtp(data || { leaderboard: {}, ctp_holes: [] });
      } catch { /* silent — poster still renders */ }
    })();
    return () => { dead = true; };
  }, [round?.id]);

  useEffect(() => {
    const t = setTimeout(() => {
      try { window.print(); } catch { /* silent */ }
    }, 300);
    return () => clearTimeout(t);
  }, []);

  const memberMap = useMemo(
    () => Object.fromEntries((members || []).map((m) => [m.id, m])),
    [members]
  );

  const ranked = useMemo(() => {
    return (scorecards || [])
      .filter((sc) => (sc.total || 0) > 0)
      .map((sc) => {
        const m = memberMap[sc.member_id];
        const holesPlayed = (sc.scores || []).filter((s) => s > 0).length;
        const net = (sc.total || 0) - (sc.handicap_at_round || 0);
        return {
          id: sc.id,
          name: m?.name || "Player",
          division: m?.division || "Open",
          total: sc.total || 0,
          plusMinus: sc.plus_minus || 0,
          handicap: sc.handicap_at_round || 0,
          net,
          holesPlayed,
        };
      })
      .sort((a, b) => {
        if (a.net !== b.net) return a.net - b.net;
        if (a.total !== b.total) return a.total - b.total;
        return b.holesPlayed - a.holesPlayed;
      });
  }, [scorecards, memberMap]);

  const top3 = ranked.slice(0, 3);
  const hotRound = useMemo(() => {
    if (!ranked.length) return null;
    return [...ranked].sort((a, b) => a.plusMinus - b.plusMinus)[0] || null;
  }, [ranked]);

  const ctpHoles = ctp.ctp_holes || [];
  const ctpWinners = useMemo(() => {
    const board = ctp.leaderboard || {};
    return ctpHoles.map((hole) => {
      const list = board[hole] || board[String(hole)] || [];
      const winner = list[0];
      return { hole, winner };
    });
  }, [ctp, ctpHoles]);

  const rankBadge = ["bg-amber-400", "bg-slate-300", "bg-amber-700 text-white"];

  return (
    <div
      className="fixed inset-0 z-[130] bg-white overflow-auto ac-recap-overlay"
      data-testid="round-recap-poster"
      role="dialog"
      aria-modal="true"
    >
      <style>{`
        @media print {
          @page { size: letter portrait; margin: 0.5in; }
          body > * { visibility: hidden !important; }
          .ac-recap-overlay, .ac-recap-overlay * { visibility: visible !important; }
          .ac-recap-overlay { position: static !important; overflow: visible !important; background: #ffffff !important; }
          .ac-recap-hide { display: none !important; }
        }
      `}</style>

      {/* On-screen toolbar */}
      <div
        className="ac-recap-hide sticky top-0 z-10 flex items-center gap-3 px-6 py-3 bg-slate-900 text-white border-b border-slate-800"
      >
        <Printer size={18} weight="duotone" className="text-amber-400" />
        <div className="font-display text-base">Print preview · Round recap</div>
        <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-400 hidden sm:block">
          Portrait letter · save as PDF supported
        </div>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => window.print()}
            data-testid="recap-print-again-btn"
            className="text-xs font-semibold text-slate-900 bg-amber-400 hover:bg-amber-500 rounded-full px-3 py-1.5 inline-flex items-center gap-1.5"
          >
            <Printer size={12} weight="duotone" />
            Print again
          </button>
          <button
            type="button"
            onClick={onClose}
            data-testid="recap-close-btn"
            className="text-xs font-semibold text-white border border-slate-500 hover:border-slate-300 rounded-full px-3 py-1.5 inline-flex items-center gap-1.5"
          >
            <X size={12} />
            Close
          </button>
        </div>
      </div>

      {/* Printable poster */}
      <div className="max-w-[8.5in] mx-auto px-8 py-8 text-slate-900">
        <header className="border-b-2 border-slate-900 pb-3 mb-6">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
                Ace Chasers · Round Recap
              </div>
              <div className="font-display text-3xl leading-tight">
                {round?.name || "Round"}
              </div>
              <div className="text-sm text-slate-600 mt-1">
                {league?.name || "League"}
                {round?.course_location ? ` · ${round.course_location}` : ""}
              </div>
            </div>
            <div className="font-mono-data text-xs text-slate-600 text-right">
              {round?.date || new Date().toLocaleDateString()}
            </div>
          </div>
        </header>

        {/* Podium — Top 3 */}
        <section className="mb-8" data-testid="recap-podium">
          <div className="flex items-center gap-2 mb-3">
            <Trophy size={18} weight="duotone" className="text-amber-600" />
            <div className="font-display text-xl">Podium · Top 3</div>
          </div>
          {top3.length === 0 ? (
            <div className="text-sm text-slate-500 italic">No completed scorecards.</div>
          ) : (
            <ol className="grid gap-2">
              {top3.map((r, i) => (
                <li
                  key={r.id}
                  className={`flex items-center gap-3 p-3 rounded border-2 ${
                    i === 0 ? "border-amber-500 bg-amber-50" : "border-slate-300"
                  }`}
                  data-testid={`recap-podium-${i + 1}`}
                >
                  <span className={`w-10 h-10 rounded-full font-display text-lg flex items-center justify-center ${rankBadge[i] || "bg-slate-200"}`}>
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-900 truncate">{r.name}</div>
                    <div className="font-mono-data text-[10px] text-slate-500 uppercase tracking-wider">
                      {r.division}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono-data text-lg font-bold">
                      {r.total}
                      <span className="text-slate-500 text-sm ml-2">
                        ({r.plusMinus >= 0 ? "+" : ""}{r.plusMinus})
                      </span>
                    </div>
                    <div className="font-mono-data text-[10px] text-slate-500 uppercase tracking-wider">
                      NET {r.net}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        {/* Hot Round callout */}
        <section className="mb-8" data-testid="recap-hot-round">
          <div className="flex items-center gap-2 mb-3">
            <Fire size={18} weight="duotone" className="text-red-600" />
            <div className="font-display text-xl">Hot Round</div>
          </div>
          {hotRound ? (
            <div className="flex items-center gap-3 p-4 rounded border-2 border-red-500 bg-red-50">
              <div className="flex-1">
                <div className="font-semibold text-slate-900 text-lg">{hotRound.name}</div>
                <div className="font-mono-data text-[10px] text-slate-500 uppercase tracking-wider mt-1">
                  Deepest score of the day
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono-data text-2xl font-bold text-red-700">
                  {hotRound.plusMinus >= 0 ? "+" : ""}{hotRound.plusMinus}
                </div>
                <div className="font-mono-data text-[10px] text-slate-500 uppercase tracking-wider">
                  Total {hotRound.total}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500 italic">No scores logged.</div>
          )}
        </section>

        {/* CTP winners */}
        <section data-testid="recap-ctp">
          <div className="flex items-center gap-2 mb-3">
            <Target size={18} weight="duotone" className="text-emerald-700" />
            <div className="font-display text-xl">Closest to Pin</div>
          </div>
          {ctpHoles.length === 0 ? (
            <div className="text-sm text-slate-500 italic">
              No CTP holes flagged on this round.
            </div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="text-left border-b-2 border-slate-900 font-mono-data text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="py-1 pr-2 w-16">Hole</th>
                  <th className="py-1 pr-2">Winner</th>
                  <th className="py-1 text-right">Distance</th>
                </tr>
              </thead>
              <tbody>
                {ctpWinners.map(({ hole, winner }) => (
                  <tr key={hole} className="border-b border-slate-200" data-testid={`recap-ctp-hole-${hole}`}>
                    <td className="py-1.5 pr-2 font-mono-data font-semibold">H{hole}</td>
                    <td className="py-1.5 pr-2">{winner ? winner.member_name : <span className="text-slate-400 italic">no entry</span>}</td>
                    <td className="py-1.5 text-right font-mono-data">
                      {winner ? `${winner.feet}' ${Number(winner.inches).toFixed(1)}"` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <footer className="mt-10 pt-3 border-t border-slate-300 flex justify-between text-[10px] font-mono-data uppercase tracking-widest text-slate-500">
          <span>Sponsored by Ace Chasers · League Ops</span>
          <span>acechasers.net</span>
        </footer>
      </div>
    </div>
  );
}
