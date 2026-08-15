import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { Trash, Warning } from "@phosphor-icons/react";
import { useRoundStore } from "@/store/roundStore";

/**
 * DeleteLeaguePanel — director-only "danger zone" section rendered
 * inside the League Settings surface (currently mounted at the bottom
 * of the Compliance tab).
 *
 * UX contract:
 *   1. A subtle text-red-600 button opens the confirmation modal.
 *   2. The modal REQUIRES the manager to retype the exact league name.
 *      The Delete button stays disabled until the input matches.
 *   3. On success the frontend clears the round store, toasts, and
 *      navigates back to `/leagues` (League List).
 *
 * The backend `DELETE /api/leagues/{id}` performs the full cascade
 * sweep across every league-scoped collection.
 */
export default function DeleteLeaguePanel({ leagueId, leagueName, isDirector }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const clearRoundStore = useRoundStore((s) => s.clear);

  if (!isDirector) return null;
  const nameOK = typed.trim() === (leagueName || "").trim() && typed.trim().length > 0;

  const closeModal = () => {
    if (busy) return;
    setOpen(false);
    setTyped("");
  };

  const runDelete = async () => {
    if (!nameOK || busy) return;
    setBusy(true);
    try {
      const { data } = await api.delete(`/leagues/${leagueId}`, {
        data: { confirm_name: typed.trim() },
      });
      // Clear any in-memory round state before we leave — otherwise a
      // stale Round Detail Header could linger on the League List.
      clearRoundStore();
      toast.success(
        `League deleted · ${data.total_docs_removed} record${data.total_docs_removed === 1 ? "" : "s"} cleaned`
      );
      // replace=true so the back button doesn't restore the dead league page.
      navigate("/leagues", { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete league");
      setBusy(false);
    }
  };

  return (
    <>
      {/* League Settings panel — Danger Zone */}
      <div
        data-testid="delete-league-panel"
        className="mt-8 rounded-2xl border border-red-200 bg-red-50/40 p-5"
      >
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-red-100 text-red-700 flex items-center justify-center flex-shrink-0">
            <Warning size={18} weight="duotone" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-red-600 mb-1">
              League Settings · Danger Zone
            </div>
            <p className="text-sm text-slate-700 mb-3">
              Permanently delete this league and every associated round,
              scorecard, ledger entry, and clubhouse post. This action
              cannot be undone.
            </p>
            <button
              type="button"
              onClick={() => setOpen(true)}
              data-testid="delete-league-btn"
              className="text-red-600 hover:text-red-800 text-sm font-medium underline underline-offset-4 decoration-red-300 hover:decoration-red-800 transition-colors"
            >
              Delete League
            </button>
          </div>
        </div>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
          data-testid="delete-league-modal"
          onClick={closeModal}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl border border-red-200 max-w-md w-full p-6 shadow-2xl"
          >
            <div className="flex items-center gap-2 mb-3">
              <Warning size={22} weight="fill" className="text-red-600" />
              <h2 className="font-display text-xl text-slate-900">
                Delete this league?
              </h2>
            </div>
            <p className="text-sm text-slate-700 mb-4">
              This will remove every round, scorecard, ledger entry, bracket,
              clubhouse post, and roster row tied to{" "}
              <span className="font-semibold text-slate-900">{leagueName}</span>.
              To confirm, type the league name exactly below.
            </p>

            <label className="block text-[10px] uppercase tracking-widest font-mono-data text-slate-500 mb-1">
              Type <span className="text-red-600">{leagueName}</span> to confirm
            </label>
            <input
              data-testid="delete-league-confirm-input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              placeholder={leagueName}
              className={`w-full rounded-lg border-2 px-3 py-2 text-sm font-mono-data text-slate-900 mb-4 focus:outline-none focus:ring-2 focus:ring-red-500/10 ${
                nameOK
                  ? "border-red-300 bg-red-50/40 focus:border-red-600"
                  : "border-slate-200 bg-slate-50 focus:border-slate-400"
              }`}
            />

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={closeModal}
                disabled={busy}
                data-testid="delete-league-cancel-btn"
                className="text-sm font-medium text-slate-600 hover:text-slate-900 px-3 py-2"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={runDelete}
                disabled={!nameOK || busy}
                data-testid="delete-league-confirm-btn"
                className={`text-sm font-semibold rounded-full px-4 py-2 transition-colors shadow-sm ${
                  nameOK && !busy
                    ? "bg-red-600 hover:bg-red-700 text-white"
                    : "bg-slate-200 text-slate-400 cursor-not-allowed"
                }`}
              >
                <Trash size={13} weight="fill" className="inline mr-1" />
                {busy ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
