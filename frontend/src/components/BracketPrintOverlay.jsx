import { useEffect } from "react";
import { X, Printer } from "@phosphor-icons/react";

/**
 * BracketPrintOverlay — full-screen printable poster view of the
 * current Match-Play bracket. Rendered inline via a fixed overlay and
 * gated by an in-page `@media print` block so hitting `window.print()`
 * only outputs this section (portrait letter, all other UI hidden).
 *
 * Directors typically click the "Print bracket" button in BracketView,
 * which mounts this component and immediately calls window.print(). The
 * on-screen preview is also useful for verifying layout before printing.
 */
export default function BracketPrintOverlay({
  bracket,
  leagueName,
  memberMap,
  onClose,
}) {
  useEffect(() => {
    // Auto-open the native print dialog once the overlay is mounted.
    // Small delay so layout has time to settle before the browser
    // captures the printable area.
    const t = setTimeout(() => {
      try { window.print(); } catch { /* silent */ }
    }, 250);
    return () => clearTimeout(t);
  }, []);

  if (!bracket) return null;
  const isDouble = bracket.kind === "double";
  const tiers = bracket.tiers || [];
  const wbTiers = bracket.wb_tiers || [];
  const lbTiers = bracket.lb_tiers || [];
  const grandFinal = bracket.grand_final;
  const nameFor = (id) => (id ? memberMap?.[id]?.name || "Player" : "BYE");

  const renderTierGroup = (label, tierList, finalName, key) => (
    <div key={key} className="mb-6">
      <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-600 mb-1">{label}</div>
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: `repeat(${Math.max(tierList.length, 1)}, minmax(0, 1fr))` }}
      >
        {tierList.map((tier, tIdx) => (
          <div key={tIdx} className="flex flex-col gap-2" data-testid={`print-${key}-tier-${tIdx}`}>
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-600 pb-1 border-b border-slate-300">
              {tIdx === tierList.length - 1 ? finalName : `Tier ${tIdx + 1}`}
            </div>
            {tier.map((m) => {
              const aWin = m.winner_id && m.winner_id === m.a_member_id;
              const bWin = m.winner_id && m.winner_id === m.b_member_id;
              return (
                <div
                  key={m.id}
                  className="border-2 border-slate-900 rounded overflow-hidden"
                  data-testid={`print-match-${m.id}`}
                >
                  <div className={`flex items-center justify-between px-2 py-1 text-sm ${aWin ? "bg-emerald-100 border-b border-emerald-500" : "border-b border-slate-300"}`}>
                    <span className={aWin ? "font-bold text-emerald-800" : "text-slate-900"}>{nameFor(m.a_member_id)}</span>
                    <span className={`font-mono-data text-xs ${aWin ? "text-emerald-800 font-bold" : "text-slate-500"}`}>{m.a_score ?? "—"}</span>
                  </div>
                  <div className={`flex items-center justify-between px-2 py-1 text-sm ${bWin ? "bg-emerald-100" : ""}`}>
                    <span className={bWin ? "font-bold text-emerald-800" : "text-slate-900"}>{nameFor(m.b_member_id)}</span>
                    <span className={`font-mono-data text-xs ${bWin ? "text-emerald-800 font-bold" : "text-slate-500"}`}>{m.b_score ?? "—"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[130] bg-white overflow-auto ac-print-overlay"
      data-testid="bracket-print-overlay"
      role="dialog"
      aria-modal="true"
    >
      {/* Print-only CSS: hide the rest of the app, show only this overlay,
          strip its scroll chrome, and force portrait letter. */}
      <style>{`
        @media print {
          @page { size: letter portrait; margin: 0.5in; }
          body > * { visibility: hidden !important; }
          .ac-print-overlay, .ac-print-overlay * { visibility: visible !important; }
          .ac-print-overlay { position: static !important; overflow: visible !important; box-shadow: none !important; background: #ffffff !important; }
          .ac-print-hide { display: none !important; }
        }
      `}</style>

      {/* Toolbar — visible on-screen only. */}
      <div
        className="ac-print-hide sticky top-0 z-10 flex items-center gap-3 px-6 py-3 bg-slate-900 text-white border-b border-slate-800"
        data-testid="bracket-print-toolbar"
      >
        <Printer size={18} weight="duotone" className="text-amber-400" />
        <div className="font-display text-base">Print preview · Match-Play bracket</div>
        <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-400 hidden sm:block">
          Portrait letter · save as PDF supported
        </div>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => window.print()}
            data-testid="bracket-print-again-btn"
            className="text-xs font-semibold text-slate-900 bg-amber-400 hover:bg-amber-500 rounded-full px-3 py-1.5 inline-flex items-center gap-1.5"
          >
            <Printer size={12} weight="duotone" />
            Print again
          </button>
          <button
            type="button"
            onClick={onClose}
            data-testid="bracket-print-close-btn"
            className="text-xs font-semibold text-white border border-slate-500 hover:border-slate-300 rounded-full px-3 py-1.5 inline-flex items-center gap-1.5"
          >
            <X size={12} />
            Close
          </button>
        </div>
      </div>

      {/* Printable canvas — portrait letter proportions. */}
      <div className="max-w-[8.5in] mx-auto px-6 py-8 text-slate-900">
        <header className="flex items-baseline justify-between border-b-2 border-slate-900 pb-3 mb-6">
          <div>
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
              Ace Chasers · Playoff Bracket
            </div>
            <div className="font-display text-2xl">
              {leagueName || "League"}
            </div>
          </div>
          <div className="font-mono-data text-xs text-slate-600 text-right">
            {new Date().toLocaleDateString(undefined, {
              year: "numeric", month: "short", day: "numeric",
            })}
          </div>
        </header>

        {/* Tier columns rendered side-by-side; wraps for tall brackets. */}
        {isDouble ? (
          <>
            {renderTierGroup("Winners bracket", wbTiers, "WB Final", "wb")}
            {lbTiers.length > 0 && renderTierGroup("Losers bracket", lbTiers, "LB Final", "lb")}
            {grandFinal && renderTierGroup("Grand Final", [[grandFinal]], "Champion", "gf")}
          </>
        ) : (
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${Math.max(tiers.length, 1)}, minmax(0, 1fr))` }}>
            {tiers.map((tier, tIdx) => (
              <div key={tIdx} className="flex flex-col gap-2" data-testid={`print-tier-${tIdx}`}>
                <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-600 pb-1 border-b border-slate-300">
                  {tIdx === tiers.length - 1 ? "Final" : `Tier ${tIdx + 1}`}
                </div>
                {tier.map((m) => {
                  const aWin = m.winner_id && m.winner_id === m.a_member_id;
                  const bWin = m.winner_id && m.winner_id === m.b_member_id;
                  return (
                    <div
                      key={m.id}
                      className="border-2 border-slate-900 rounded overflow-hidden"
                      data-testid={`print-match-${m.id}`}
                    >
                      <div
                        className={`flex items-center justify-between px-2 py-1 text-sm ${
                          aWin ? "bg-emerald-100 border-b border-emerald-500" : "border-b border-slate-300"
                        }`}
                      >
                        <span className={aWin ? "font-bold text-emerald-800" : "text-slate-900"}>
                          {nameFor(m.a_member_id)}
                        </span>
                        <span className={`font-mono-data text-xs ${aWin ? "text-emerald-800 font-bold" : "text-slate-500"}`}>
                          {m.a_score ?? "—"}
                        </span>
                      </div>
                      <div
                        className={`flex items-center justify-between px-2 py-1 text-sm ${
                          bWin ? "bg-emerald-100" : ""
                        }`}
                      >
                        <span className={bWin ? "font-bold text-emerald-800" : "text-slate-900"}>
                          {nameFor(m.b_member_id)}
                        </span>
                        <span className={`font-mono-data text-xs ${bWin ? "text-emerald-800 font-bold" : "text-slate-500"}`}>
                          {m.b_score ?? "—"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}

        <footer className="mt-8 pt-3 border-t border-slate-300 flex justify-between text-[10px] font-mono-data uppercase tracking-widest text-slate-500">
          <span>Winners in emerald · advance right</span>
          <span>acechasers.net</span>
        </footer>
      </div>
    </div>
  );
}
