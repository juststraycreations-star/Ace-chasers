import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { Trash, Warning, CircleNotch } from "@phosphor-icons/react";
import { useRoundStore } from "@/store/roundStore";

/**
 * DeleteLeaguePanel — director-only "danger zone" section rendered
 * inside the League Settings surface (currently mounted at the bottom
 * of the Compliance tab).
 *
 * Visual spec (Iteration 60 polish):
 *   • Modal: crisp white overlay, rounded-xl, shadow-2xl, border border-gray-100.
 *   • Destructive warnings: bg-red-50 text-red-700 — used only for the
 *     "cannot be undone" callout so the rest of the app's clean canvas
 *     stays untouched.
 *   • Delete button: gray disabled state → vibrant red the instant the
 *     typed name matches (transition-colors gives the "millisecond" feel).
 *   • Loading state: replaces button label with a spinning `CircleNotch`
 *     and drops opacity so a manager can see the sweep is in flight and
 *     can't accidentally submit twice.
 *   • Success: top-of-viewport toast + roundStore clear + redirect
 *     back to the League List.
 */
export default function DeleteLeaguePanel({ leagueId, leagueName, isDirector }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const clearRoundStore = useRoundStore((s) => s.clear);

  if (!isDirector) return null;
  const nameOK =
    typed.trim() === (leagueName || "").trim() && typed.trim().length > 0;

  const closeModal = () => {
    if (busy) return;
    setOpen(false);
    setTyped("");
  };

  const runDelete = async () => {
    if (!nameOK || busy) return;
    setBusy(true);
    try {
      await api.delete(`/leagues/${leagueId}`, {
        data: { confirm_name: typed.trim() },
      });
      // Clear any in-memory round state before we leave — otherwise a
      // stale Round Detail Header could linger on the League List.
      clearRoundStore();
      // Success banner at the top of the viewport — copy is fixed per
      // the manager brief so the message reads consistently every time
      // a league is destroyed.
      toast.success("League successfully permanently removed from database.", {
        position: "top-center",
        duration: 5000,
        "data-testid": "delete-league-success-toast",
      });
      // replace:true so the back button doesn't restore the dead page.
      navigate("/leagues", { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete league");
      setBusy(false);
    }
  };

  return (
    <>
      {/* League Settings · Danger Zone */}
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
          className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4"
          data-testid="delete-league-modal"
          onClick={closeModal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-league-modal-title"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-xl shadow-2xl border border-gray-100 max-w-md w-full p-6"
          >
            {/* Header */}
            <div className="flex items-center gap-2 mb-3">
              <div className="w-10 h-10 rounded-full bg-red-50 text-red-700 flex items-center justify-center">
                <Warning size={22} weight="fill" />
              </div>
              <h2
                id="delete-league-modal-title"
                className="font-display text-xl text-slate-900"
              >
                Delete this league?
              </h2>
            </div>

            {/* Destructive callout — red palette is reserved for THIS block */}
            <div
              className="mb-4 rounded-lg bg-red-50 text-red-700 border border-red-100 p-3 text-sm leading-relaxed"
              data-testid="delete-league-warning"
            >
              This permanently removes every round, scorecard, ledger entry,
              bracket, clubhouse post, and roster row tied to{" "}
              <span className="font-semibold">{leagueName}</span>. This action
              cannot be undone.
            </div>

            {/* Confirmation input */}
            <label className="block text-[10px] uppercase tracking-widest font-mono-data text-slate-500 mb-1">
              Type <span className="text-red-600">{leagueName}</span> to confirm
            </label>
            <input
              data-testid="delete-league-confirm-input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              disabled={busy}
              placeholder={leagueName}
              className={`w-full rounded-lg border-2 px-3 py-2 text-sm font-mono-data text-slate-900 mb-5 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500/10 disabled:opacity-60 ${
                nameOK
                  ? "border-red-300 bg-red-50/40 focus:border-red-600"
                  : "border-gray-200 bg-gray-50 focus:border-gray-400"
              }`}
            />

            {/* Action row */}
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={closeModal}
                disabled={busy}
                data-testid="delete-league-cancel-btn"
                className="text-sm font-medium text-slate-600 hover:text-slate-900 px-3 py-2 rounded-full transition-colors disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={runDelete}
                disabled={!nameOK || busy}
                data-testid="delete-league-confirm-btn"
                aria-busy={busy || undefined}
                className={`text-sm font-semibold rounded-full px-4 py-2 shadow-sm inline-flex items-center justify-center gap-2 min-w-[168px] transition-colors ${
                  busy
                    ? "bg-red-600 text-white opacity-70 cursor-wait"
                    : nameOK
                    ? "bg-red-600 hover:bg-red-700 text-white cursor-pointer"
                    : "bg-gray-100 text-gray-400 cursor-not-allowed"
                }`}
              >
                {busy ? (
                  <>
                    <CircleNotch
                      size={14}
                      weight="bold"
                      className="animate-spin"
                      data-testid="delete-league-spinner"
                    />
                    <span>Deleting…</span>
                  </>
                ) : (
                  <>
                    <Trash size={13} weight="fill" />
                    Delete permanently
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
