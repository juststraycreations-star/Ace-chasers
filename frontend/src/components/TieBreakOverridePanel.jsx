import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Warning, Trophy, X } from "@phosphor-icons/react";

/**
 * TieBreakOverridePanel — high-visibility director override that opens
 * when a Match-Play scorecard finalize returns `bracket_advance.tied`.
 *
 * Auto-advancement is blocked server-side on ties. This panel lets the
 * director immediately pick the sudden-death playoff winner and resolve
 * the match node manually.
 *
 * On success it calls `POST /api/bracket/matches/{match_id}/report`
 * (the same endpoint used by the regular bracket UI), then `onResolved()`
 * so the caller can close the panel and re-fetch bracket state.
 */
export default function TieBreakOverridePanel({
  tie,          // { match_id, a_member_id, b_member_id, a_total, b_total }
  memberMap,
  onResolved,
  onClose,
}) {
  const [submitting, setSubmitting] = useState(false);
  const [selection, setSelection] = useState(null);

  if (!tie || !tie.match_id) return null;

  const aName = memberMap?.[tie.a_member_id]?.name || "Player A";
  const bName = memberMap?.[tie.b_member_id]?.name || "Player B";

  const resolve = async (winnerId) => {
    if (submitting) return;
    setSelection(winnerId);
    setSubmitting(true);
    try {
      await api.post(`/bracket/matches/${tie.match_id}/report`, {
        winner_id: winnerId,
        a_score: tie.a_total,
        b_score: tie.b_total,
      });
      toast.success("Tie-break resolved · winner advanced");
      onResolved?.(winnerId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Tie-break failed");
      setSelection(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[120] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="tiebreak-override-panel"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl border-2 border-amber-500 overflow-hidden">
        <div className="bg-amber-500 text-slate-900 px-5 py-3 flex items-center gap-2">
          <Warning size={22} weight="fill" />
          <div className="font-display text-lg">Match Play tie · director override</div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              data-testid="tiebreak-close-btn"
              className="ml-auto text-slate-900/70 hover:text-slate-900"
              aria-label="Close"
            >
              <X size={20} />
            </button>
          )}
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-slate-700">
            Both players finalized at the same total — auto-advancement is
            blocked. Select the <strong>sudden-death playoff winner</strong> to
            resolve this match node.
          </p>
          <div className="grid gap-3">
            {[
              { id: tie.a_member_id, name: aName, total: tie.a_total },
              { id: tie.b_member_id, name: bName, total: tie.b_total },
            ].map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => resolve(p.id)}
                disabled={submitting}
                data-testid={`tiebreak-select-${p.id}`}
                className={`w-full flex items-center justify-between gap-3 p-4 rounded-xl border-2 transition-colors text-left ${
                  selection === p.id
                    ? "border-emerald-500 bg-emerald-50"
                    : "border-slate-200 hover:border-amber-500 hover:bg-amber-50"
                } disabled:opacity-50 disabled:cursor-wait`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Trophy
                    size={22}
                    weight={selection === p.id ? "fill" : "duotone"}
                    className={selection === p.id ? "text-emerald-600" : "text-amber-600"}
                  />
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-900 truncate">{p.name}</div>
                    <div className="font-mono-data text-[11px] text-slate-500 uppercase tracking-wider">
                      Total {p.total}
                    </div>
                  </div>
                </div>
                <span className="font-mono-data text-xs text-amber-700 font-semibold">
                  {selection === p.id ? "Advancing…" : "Declare winner"}
                </span>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-500 font-mono-data uppercase tracking-wider">
            Logged to Proof of Score · reversible with a bracket re-seed
          </p>
        </div>
      </div>
    </div>
  );
}
