import { useEffect, useMemo } from "react";
import { X, Printer } from "@phosphor-icons/react";
import ScorecardGrid from "@/components/ScorecardGrid";

/**
 * BulkScorecardPrintOverlay — director-only "Print All Tournament
 * Scorecards" flow. Groups every scorecard on the round by its parent
 * `card_id`, renders a read-only ScorecardGrid per group with a
 * page-break between each, then auto-fires `window.print()`.
 *
 * The overlay is print-CSS gated: while on screen, a toolbar with
 * "Print again" / "Close" is visible; when the print dialog is invoked
 * only the stacked grids paint on the page (see the `@media print`
 * block below — it hides everything outside `.ac-bulk-print-overlay`
 * and drops page-break-after on every grid group).
 *
 * The component preserves the strict P0 layout constraint (green
 * ScorecardGrid == PDF export) by delegating rendering to the exact
 * same ScorecardGrid component used on the completed-round view.
 */
export default function BulkScorecardPrintOverlay({
  league,
  round,
  scorecards,
  cards,
  memberMap,
  onClose,
}) {
  // Group scorecards by card_id. Any scorecard without a card_id is
  // bucketed under "solo" so we still print the tournament in full.
  const groups = useMemo(() => {
    const byCard = new Map();
    for (const sc of scorecards || []) {
      const key = sc.card_id || "__solo__";
      if (!byCard.has(key)) byCard.set(key, []);
      byCard.get(key).push(sc);
    }
    const cardById = new Map((cards || []).map((c) => [c.id, c]));
    const list = Array.from(byCard.entries()).map(([cardId, group]) => ({
      cardId,
      label: cardId === "__solo__" ? "Solo Cards" : (cardById.get(cardId)?.label || "Card"),
      scorecards: group,
    }));
    // Preserve the original card order the director sees on-screen.
    const order = new Map((cards || []).map((c, i) => [c.id, i]));
    list.sort((a, b) => (order.get(a.cardId) ?? 9999) - (order.get(b.cardId) ?? 9999));
    return list;
  }, [scorecards, cards]);

  // Auto-fire the native print dialog once mounted. Small delay so the
  // layout can settle before the browser snapshots.
  useEffect(() => {
    const t = setTimeout(() => {
      try { window.print(); } catch { /* silent */ }
    }, 350);
    return () => clearTimeout(t);
  }, []);

  const totalCards = groups.length;

  return (
    <div
      className="fixed inset-0 z-[130] bg-white overflow-auto ac-bulk-print-overlay"
      data-testid="bulk-scorecard-print-overlay"
      role="dialog"
      aria-modal="true"
    >
      {/* Print-only CSS. Hides all sibling app chrome, forces landscape
          letter (scorecards are wider than they are tall), and gives
          every card group its own physical page. */}
      <style>{`
        @media print {
          @page { size: letter landscape; margin: 0.4in; }
          body > * { visibility: hidden !important; }
          .ac-bulk-print-overlay, .ac-bulk-print-overlay * { visibility: visible !important; }
          .ac-bulk-print-overlay { position: static !important; overflow: visible !important; background: #ffffff !important; box-shadow: none !important; }
          .ac-bulk-print-hide { display: none !important; }
          .ac-bulk-card-group { page-break-after: always; break-after: page; }
          .ac-bulk-card-group:last-child { page-break-after: auto; break-after: auto; }
        }
      `}</style>

      {/* On-screen toolbar */}
      <div
        className="ac-bulk-print-hide sticky top-0 z-10 flex items-center gap-3 px-6 py-3 bg-slate-900 text-white border-b border-slate-800"
        data-testid="bulk-print-toolbar"
      >
        <Printer size={18} weight="duotone" className="text-amber-400" />
        <div className="font-display text-base">
          Print all tournament scorecards
        </div>
        <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-400 hidden sm:block">
          {totalCards} card{totalCards === 1 ? "" : "s"} · landscape letter · save as PDF supported
        </div>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => window.print()}
            data-testid="bulk-print-again-btn"
            className="text-xs font-semibold text-slate-900 bg-amber-400 hover:bg-amber-500 rounded-full px-3 py-1.5 inline-flex items-center gap-1.5"
          >
            <Printer size={12} weight="duotone" />
            Print again
          </button>
          <button
            type="button"
            onClick={onClose}
            data-testid="bulk-print-close-btn"
            className="text-xs font-semibold text-white border border-slate-500 hover:border-slate-300 rounded-full px-3 py-1.5 inline-flex items-center gap-1.5"
          >
            <X size={12} />
            Close
          </button>
        </div>
      </div>

      {/* Stacked ScorecardGrids — one per card, page-break between */}
      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        {totalCards === 0 && (
          <div className="text-slate-500 text-sm text-center py-8" data-testid="bulk-print-empty">
            No scorecards yet on this round.
          </div>
        )}
        {groups.map((g) => (
          <div
            key={g.cardId}
            className="ac-bulk-card-group"
            data-testid={`bulk-print-group-${g.cardId}`}
          >
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500 mb-2">
              {g.label} · {g.scorecards.length} player{g.scorecards.length === 1 ? "" : "s"}
            </div>
            <ScorecardGrid
              league={league}
              round={round}
              scorecards={g.scorecards}
              memberMap={memberMap}
              distances={round?.distances_per_hole}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
