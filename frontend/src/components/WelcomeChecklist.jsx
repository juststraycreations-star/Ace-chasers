import { QrCode, Gear, MegaphoneSimple, ArrowRight, CheckCircle } from "@phosphor-icons/react";

/**
 * WelcomeChecklist
 * ─────────────────────────────────────────────────────────────────
 * A scannable, professional quick-start module for league managers.
 * Pinned to the top of the manager workspace. Slate-gray minimalist
 * theme, clean iconography, one-click actions per operation.
 *
 * Steps:
 *   1. Generate a Round QR check-in code
 *   2. Configure the active scoring engine (format)
 *   3. Post an update to the clubhouse feed
 */
export default function WelcomeChecklist({
  managerName,
  onGenerateQr,
  onConfigureScoring,
  onPostUpdate,
  completed = {},
}) {
  const steps = [
    {
      key: "qr",
      icon: QrCode,
      title: "Generate a Round QR",
      hint: "Print or share a check-in code so players self-enroll in seconds.",
      cta: "Create QR",
      onClick: onGenerateQr,
      testid: "welcome-step-qr",
    },
    {
      key: "scoring",
      icon: Gear,
      title: "Configure scoring engine",
      hint: "Pick Singles (stroke), Doubles (best-disc), or Bracket match play.",
      cta: "Configure",
      onClick: onConfigureScoring,
      testid: "welcome-step-scoring",
    },
    {
      key: "post",
      icon: MegaphoneSimple,
      title: "Post to the clubhouse feed",
      hint: "Announce round dates, payouts, and results to every member.",
      cta: "Post update",
      onClick: onPostUpdate,
      testid: "welcome-step-post",
    },
  ];

  const done = steps.filter((s) => completed[s.key]).length;

  return (
    <section
      className="bg-slate-50 border border-slate-200 rounded-2xl p-5 sm:p-6 mb-6"
      data-testid="welcome-checklist"
      aria-label="Manager quick-start checklist"
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="font-mono-data text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">
            Manager workspace
          </div>
          <h2 className="font-display text-xl sm:text-2xl text-slate-900 tracking-tight">
            {managerName ? `Welcome, ${managerName}` : "Welcome"}
          </h2>
          <p className="text-sm text-slate-600 mt-1">
            Three quick actions to get your league running today.
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
            Progress
          </div>
          <div className="font-display text-2xl text-slate-900" data-testid="welcome-progress">
            {done}<span className="text-slate-400">/{steps.length}</span>
          </div>
        </div>
      </div>

      <ol className="grid gap-3 sm:grid-cols-3">
        {steps.map((s) => {
          const Icon = s.icon;
          const isDone = !!completed[s.key];
          return (
            <li
              key={s.key}
              className={`rounded-xl border p-4 transition-colors ${
                isDone
                  ? "bg-emerald-50 border-emerald-200"
                  : "bg-white border-slate-200 hover:border-slate-300"
              }`}
              data-testid={s.testid}
            >
              <div className="flex items-center gap-2 mb-2">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    isDone ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {isDone ? <CheckCircle size={18} weight="fill" /> : <Icon size={18} weight="duotone" />}
                </div>
                <div className="font-semibold text-sm text-slate-900">{s.title}</div>
              </div>
              <p className="text-xs text-slate-600 leading-snug mb-3" title={s.hint}>
                {s.hint}
              </p>
              <button
                type="button"
                onClick={s.onClick}
                disabled={!s.onClick}
                data-testid={`${s.testid}-btn`}
                className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isDone ? "Done" : s.cta}
                {!isDone && <ArrowRight size={12} weight="bold" />}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
