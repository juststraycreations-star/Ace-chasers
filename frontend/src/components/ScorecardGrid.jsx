import DiscIcon from "./DiscIcon";

/**
 * ScorecardGrid — UDisc-style tabular scorecard rendered in the Ace
 * Chasers green brand palette. This is a *display* component (read-
 * only); the interactive per-hole scoring UI lives on RoundScorecard's
 * default view. Use this as a printable/summary view.
 *
 * Layout (mobile ⇢ horizontal scroll):
 *   ┌─────────────────────── HEADER ───────────────────────┐
 *   │  [Disc] AceChasers    Course Name (deep emerald)     │
 *   │                       Location · League · Format     │
 *   └──────────────────────────────────────────────────────┘
 *   ┌────────┬───┬───┬───┬─  ...  ─┬────────┐
 *   │ HOLE   │ 1 │ 2 │ 3 │         │ TOT    │  ← sticky emerald column
 *   │ PAR    │ 3 │ 4 │ 3 │         │ 54     │
 *   │ DIST   │…  │…  │…  │         │        │
 *   │ Alice  │ 2 │ 5 │ 3 │         │ 55 · +1│
 *   │ Bob    │ 3 │ 3 │ 4 │         │ 58 · +4│
 *   └────────┴───┴───┴───┴─  ...  ─┴────────┘
 *
 * Score cell coloring (disc-golf convention):
 *   Eagle-or-better  → deep tournament blue bg + white
 *   Birdie           → vibrant green bg + white
 *   Par              → white / very light mint
 *   Bogey            → soft orange bg
 *   Double+ Bogey    → deep brick red bg + white
 */

function relClass(score, par) {
  if (!score || !par) return "bg-white text-slate-800";
  const diff = score - par;
  if (diff <= -2) return "bg-blue-800 text-white ring-1 ring-blue-900 font-bold";
  if (diff === -1) return "bg-green-500 text-white font-semibold";
  if (diff === 0) return "bg-emerald-50/60 text-slate-800";
  if (diff === 1) return "bg-orange-100 text-orange-900";
  return "bg-red-700 text-white font-semibold"; // double+ bogey
}

function relLabel(total, par) {
  if (!total || !par) return "";
  const d = total - par;
  if (d === 0) return "E";
  return d > 0 ? `+${d}` : `${d}`;
}

export default function ScorecardGrid({
  league,
  round,
  scorecards = [],
  memberMap = {},
  distances = null, // optional per-hole distances (feet)
  className = "",
}) {
  if (!round) return null;
  const holes = round.par_per_hole || [];
  const totalPar = holes.reduce((s, p) => s + p, 0);
  const format = league?.format || "Singles";
  const isDoubles = /double|team/i.test(format);
  const gameType = isDoubles ? "Doubles" : "Singles";

  // Column widths — kept fixed so the grid stays crisp on horizontal
  // scroll. Sticky first + last columns pin the label and the total.
  const HOLE_COL_W = 78;
  const CELL_W = 38;
  const TOTAL_COL_W = 82;

  return (
    <div
      className={`bg-white text-slate-900 rounded-2xl border border-emerald-100 shadow-sm overflow-hidden ${className}`}
      data-testid="scorecard-grid"
    >
      {/* ============= Header ============= */}
      <div className="px-5 sm:px-6 py-4 bg-gradient-to-r from-emerald-50 to-white border-b border-emerald-100">
        <div className="flex items-start gap-3">
          <div
            className="shrink-0 h-10 w-10 sm:h-12 sm:w-12 rounded-full bg-emerald-900 text-white flex items-center justify-center shadow-sm ring-2 ring-emerald-100"
            data-testid="scorecard-grid-logo"
            aria-hidden="true"
          >
            <DiscIcon size={22} weight="fill" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-mono uppercase tracking-[0.24em] text-emerald-700 mb-0.5">
              Ace Chasers
            </div>
            <div
              className="font-display text-xl sm:text-2xl leading-tight text-emerald-950 truncate"
              data-testid="scorecard-grid-course"
            >
              {round.name || league?.name || "Round"}
            </div>
            <div
              className="text-xs text-slate-500 mt-0.5 truncate"
              data-testid="scorecard-grid-location"
            >
              {league?.location || "—"}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
              {league?.name && (
                <span
                  data-testid="scorecard-grid-league-tag"
                  className="inline-flex items-center px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-semibold"
                >
                  {league.name}
                </span>
              )}
              <span className="text-slate-600" data-testid="scorecard-grid-game-type">
                {gameType}
              </span>
              {round.date && (
                <span className="text-slate-500">
                  · {new Date(round.date).toLocaleDateString()}
                </span>
              )}
            </div>
            {scorecards.length > 0 && (
              <div
                className="mt-2 text-[11px] text-slate-500 truncate"
                data-testid="scorecard-grid-players"
              >
                Card: {scorecards.map((sc) => memberMap[sc.member_id]?.name || "Player").join(" · ")}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ============= Grid body ============= */}
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <colgroup>
            <col style={{ width: HOLE_COL_W }} />
            {holes.map((_, i) => (
              <col key={i} style={{ width: CELL_W }} />
            ))}
            <col style={{ width: TOTAL_COL_W }} />
          </colgroup>

          {/* Hole numbers row */}
          <thead>
            <tr>
              <th
                scope="col"
                className="sticky left-0 z-10 bg-emerald-50 text-emerald-900 border border-emerald-100 px-2 py-2 text-left font-mono text-[10px] uppercase tracking-wider"
              >
                Hole
              </th>
              {holes.map((_, i) => (
                <th
                  key={i}
                  scope="col"
                  className="border border-emerald-100 bg-green-50/50 text-center font-mono text-xs text-emerald-900 py-2"
                  data-testid={`grid-hole-${i + 1}`}
                >
                  {i + 1}
                </th>
              ))}
              <th
                scope="col"
                className="sticky right-0 z-10 bg-emerald-800 text-white border border-emerald-800 px-2 py-2 text-center font-mono text-[10px] uppercase tracking-wider"
              >
                Total
              </th>
            </tr>
          </thead>

          <tbody>
            {/* Par row */}
            <tr>
              <th
                scope="row"
                className="sticky left-0 z-10 bg-emerald-50 text-emerald-900 border border-emerald-100 px-2 py-1.5 text-left font-mono text-[10px] uppercase tracking-wider"
              >
                Par
              </th>
              {holes.map((p, i) => (
                <td
                  key={i}
                  className="border border-emerald-100 text-center text-slate-700 font-mono tabular-nums py-1.5"
                  data-testid={`grid-par-${i + 1}`}
                >
                  {p}
                </td>
              ))}
              <td className="sticky right-0 z-10 bg-emerald-800 text-white border border-emerald-800 text-center font-bold tabular-nums py-1.5">
                {totalPar}
              </td>
            </tr>

            {/* Distance row (optional) */}
            {distances && distances.length === holes.length && (
              <tr>
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-emerald-50 text-emerald-900 border border-emerald-100 px-2 py-1.5 text-left font-mono text-[10px] uppercase tracking-wider"
                >
                  Dist
                </th>
                {distances.map((d, i) => (
                  <td
                    key={i}
                    className="border border-emerald-100 text-center text-slate-500 font-mono text-[11px] tabular-nums py-1.5"
                    data-testid={`grid-dist-${i + 1}`}
                  >
                    {d || "—"}
                  </td>
                ))}
                <td className="sticky right-0 z-10 bg-emerald-800/90 text-white border border-emerald-800 text-center font-mono text-[11px] py-1.5">
                  —
                </td>
              </tr>
            )}

            {/* One row per scorecard */}
            {scorecards.map((sc) => {
              const m = memberMap[sc.member_id];
              const name = m?.name || "Player";
              const scores = sc.scores || [];
              const total = sc.total || scores.reduce((s, n) => s + (Number(n) || 0), 0);
              const rel = relLabel(total, totalPar);
              return (
                <tr key={sc.id} data-testid={`grid-scorecard-row-${sc.id}`}>
                  <th
                    scope="row"
                    className="sticky left-0 z-10 bg-white border border-emerald-100 px-2 py-1.5 text-left font-medium text-slate-800 truncate"
                    style={{ maxWidth: HOLE_COL_W }}
                    title={name}
                  >
                    {name}
                  </th>
                  {holes.map((par, i) => {
                    const s = Number(scores[i]) || 0;
                    return (
                      <td
                        key={i}
                        className={`border border-emerald-100 text-center font-mono tabular-nums py-1.5 ${relClass(s, par)}`}
                        data-testid={`grid-score-${sc.id}-${i + 1}`}
                        title={s ? `Hole ${i + 1}: ${s} (${relLabel(s, par)})` : `Hole ${i + 1}: —`}
                      >
                        {s || "—"}
                      </td>
                    );
                  })}
                  <td
                    className="sticky right-0 z-10 bg-emerald-800 text-white border border-emerald-800 text-center font-bold tabular-nums py-1.5 whitespace-nowrap px-2"
                    data-testid={`grid-total-${sc.id}`}
                  >
                    {total}
                    {rel && (
                      <span className="ml-1.5 text-[11px] font-mono text-emerald-100/90">{rel}</span>
                    )}
                  </td>
                </tr>
              );
            })}

            {scorecards.length === 0 && (
              <tr>
                <td
                  colSpan={holes.length + 2}
                  className="text-center text-slate-400 italic py-6 text-xs"
                  data-testid="grid-empty"
                >
                  No scorecards on this round yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ============= Legend ============= */}
      <div className="px-5 sm:px-6 py-3 border-t border-emerald-100 bg-emerald-50/40 flex flex-wrap gap-2 text-[10px] font-mono uppercase tracking-wider">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-blue-800" /> Eagle+
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-green-500" /> Birdie
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-emerald-50 border border-emerald-100" /> Par
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-orange-100 border border-orange-300" /> Bogey
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-red-700" /> Double+
        </span>
      </div>
    </div>
  );
}
