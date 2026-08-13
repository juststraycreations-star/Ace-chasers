import RoundQRPanel from "@/components/RoundQRPanel";
import {
  CheckCircle,
  PlayCircle,
  QrCode,
} from "@phosphor-icons/react";

/**
 * RoundCard — single source of truth for how a round row renders on the
 * League Dashboard. Three visual variants match the three temporal
 * lifecycle groups in the Rounds tab:
 *
 *   active    → green-bordered priority card with Open / Finalize / QR
 *   upcoming  → minimalist white row with Open / Start
 *   completed → compact archive row with Winner chip + PDF Scorecard link
 *
 * Callers own state (director flag, QR panel toggle, action handlers)
 * and pass them in. This keeps the component pure and easy to re-theme.
 */

const primaryBtn =
  "inline-flex items-center gap-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm px-4 py-2 shadow-sm transition-colors";
const secondaryBtn =
  "inline-flex items-center gap-1.5 rounded-full bg-white text-slate-800 border border-slate-300 hover:border-slate-500 font-semibold text-sm px-4 py-2 transition-colors";

export default function RoundCard({
  variant, // "active" | "upcoming" | "completed"
  round,
  isDirector,
  qrOpen,
  onOpenScorecard,
  onFinalize,
  onStart,
  onToggleQR,
}) {
  const date = new Date(round.date).toLocaleDateString();

  if (variant === "active") {
    return (
      <div
        data-testid={`round-card-active-${round.id}`}
        className="rounded-2xl border-2 border-emerald-500 bg-white shadow-md p-6 mb-3"
      >
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div>
            <div className="font-display text-2xl text-slate-900">{round.name}</div>
            <div className="text-xs text-slate-500 mt-1 font-mono-data uppercase tracking-wider">
              {date} · {round.holes} holes
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200 px-3 py-1 text-[10px] font-mono-data uppercase tracking-widest font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            LIVE
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            data-testid={`round-open-${round.id}`}
            onClick={onOpenScorecard}
            className={primaryBtn}
          >
            Open Scorecard
          </button>
          {isDirector && (
            <button
              data-testid={`round-complete-${round.id}`}
              onClick={onFinalize}
              className={secondaryBtn}
            >
              <CheckCircle size={14} weight="fill" className="text-emerald-600" />
              Finalize
            </button>
          )}
          {isDirector && (
            <button
              data-testid={`round-qr-btn-${round.id}`}
              onClick={onToggleQR}
              className={secondaryBtn}
              title="Show a QR code for players to self-enroll on this round"
            >
              <QrCode size={14} weight="bold" className="text-emerald-600" />
              {qrOpen ? "Hide QR" : "Check-In QR"}
            </button>
          )}
        </div>
        {qrOpen && (
          <div className="mt-4" data-testid={`round-qr-wrapper-${round.id}`}>
            <RoundQRPanel roundId={round.id} roundName={round.name} />
          </div>
        )}
      </div>
    );
  }

  if (variant === "upcoming") {
    return (
      <li
        data-testid={`round-card-upcoming-${round.id}`}
        className="rounded-xl border border-slate-200 bg-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap hover:border-slate-300 transition-colors"
      >
        <div className="min-w-0">
          <div className="font-display text-base text-slate-900 truncate">{round.name}</div>
          <div className="text-xs text-slate-500 font-mono-data uppercase tracking-wider mt-0.5">
            {date} · {round.holes} holes
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            data-testid={`round-open-${round.id}`}
            onClick={onOpenScorecard}
            className={secondaryBtn}
          >
            Open Scorecard
          </button>
          {isDirector && (
            <button
              data-testid={`round-start-${round.id}`}
              onClick={onStart}
              className={primaryBtn}
            >
              <PlayCircle size={14} weight="fill" /> Start
            </button>
          )}
        </div>
      </li>
    );
  }

  // completed
  const winnerName = round.winner_name || null;
  return (
    <li
      data-testid={`round-card-completed-${round.id}`}
      className="flex items-center justify-between gap-3 flex-wrap px-4 py-3"
    >
      <div className="min-w-0 flex items-center gap-2 flex-wrap">
        <div className="min-w-0">
          <div className="font-display text-sm text-slate-900 truncate">{round.name}</div>
          <div className="text-[11px] text-slate-500 font-mono-data uppercase tracking-wider">
            {date}
          </div>
        </div>
        {winnerName ? (
          <span
            data-testid={`round-winner-chip-${round.id}`}
            title="Round winner (hot-round finisher)"
            className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 px-2.5 py-0.5 text-[10px] font-mono-data uppercase tracking-widest font-semibold"
          >
            <CheckCircle size={11} weight="fill" className="text-emerald-600" />
            Winner · {winnerName}
          </span>
        ) : (
          <span
            data-testid={`round-winner-chip-${round.id}`}
            className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 border border-slate-200 text-slate-500 px-2.5 py-0.5 text-[10px] font-mono-data uppercase tracking-widest"
          >
            Winner · —
          </span>
        )}
      </div>
      <button
        data-testid={`round-pdf-${round.id}`}
        onClick={onOpenScorecard}
        className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs px-3 py-1.5 shadow-sm transition-colors"
      >
        PDF Scorecard
      </button>
    </li>
  );
}
