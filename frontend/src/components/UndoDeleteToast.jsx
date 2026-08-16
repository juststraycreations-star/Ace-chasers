import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowCounterClockwise, Warning } from "@phosphor-icons/react";
import api from "@/lib/api";

/**
 * UndoDeleteToast — the 30-second in-page undo window for a deleted
 * league. Rendered via `sonner.toast.custom()` from `spawnUndoToast()`
 * below so it survives navigation from `LeagueDetail` → `LeagueList`.
 *
 * UX contract:
 *   • Toast reads: "League deleted. Mistake? [Undo] (Ns remaining)".
 *   • Countdown ticks 30 → 0 in the toast label; toast dismisses itself
 *     at 0. The initial DELETE has already run server-side, so the
 *     30s is a client-side confidence window on top of the 30-day
 *     server-side retention lock.
 *   • Tapping Undo:
 *       1) Cancels the ticker immediately.
 *       2) POSTs to /api/leagues/restore with the audit id.
 *       3) On success, dismisses the toast, fires a confirmation
 *          toast, and calls `onRestored({ league_id, league_name })`
 *          so the League List can splice the row back in.
 */
function UndoDeleteToast({ toastId, auditId, leagueName, onRestored }) {
  const [secondsLeft, setSecondsLeft] = useState(30);
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    if (restoring) return undefined;
    const t = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(t);
          // Timer expired without action — dismiss ourselves. The
          // server-side deletion has already run; the 30-day retention
          // lock still lets the manager restore later via the audit
          // listing, but the in-page fast path is gone.
          toast.dismiss(toastId);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [restoring, toastId]);

  const runUndo = async () => {
    if (restoring) return;
    setRestoring(true);
    try {
      const { data } = await api.post("/leagues/restore", { audit_id: auditId });
      toast.dismiss(toastId);
      toast.success(`Restored · ${data.total_docs_restored} record${data.total_docs_restored === 1 ? "" : "s"} back in place`, {
        position: "top-center",
        duration: 4000,
      });
      onRestored?.({
        league_id: data.league_id,
        league_name: data.league_name,
        audit_id: auditId,
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Restore failed");
      setRestoring(false);
    }
  };

  const pct = Math.max(0, Math.min(1, secondsLeft / 30));

  return (
    <div
      data-testid="undo-delete-toast"
      className="w-full sm:w-[420px] bg-slate-900 text-white rounded-xl shadow-2xl border border-slate-700 overflow-hidden"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="w-9 h-9 rounded-full bg-red-500/15 text-red-300 flex items-center justify-center flex-shrink-0">
          <Warning size={18} weight="duotone" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold leading-tight">League deleted.</div>
          <div className="text-xs text-slate-300 truncate">
            {leagueName ? `${leagueName} · ` : ""}Mistake?{" "}
            <span className="font-mono-data text-emerald-300" data-testid="undo-delete-countdown">
              ({secondsLeft}s remaining)
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={runUndo}
          disabled={restoring || secondsLeft <= 0}
          data-testid="undo-delete-btn"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-900 bg-emerald-400 hover:bg-emerald-300 rounded-full px-3 py-2 shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ArrowCounterClockwise size={13} weight="bold" />
          {restoring ? "Restoring…" : "Undo"}
        </button>
      </div>
      {/* Countdown progress bar — visual reinforcement of the timer */}
      <div className="h-1 bg-slate-800">
        <div
          className="h-full bg-emerald-400 transition-all duration-1000 ease-linear"
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}

/**
 * spawnUndoToast — imperative helper so the deletion handler can fire
 * the countdown without turning `DeleteLeaguePanel` into a JSX host.
 */
export function spawnUndoToast({ auditId, leagueName, onRestored }) {
  toast.custom(
    (id) => (
      <UndoDeleteToast
        toastId={id}
        auditId={auditId}
        leagueName={leagueName}
        onRestored={onRestored}
      />
    ),
    {
      position: "bottom-center",
      duration: 30_000, // matches the countdown; the ticker also dismisses at 0
    }
  );
}

export default UndoDeleteToast;
