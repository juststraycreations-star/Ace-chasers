import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import FirstRunBadge from "./FirstRunBadge";
import { X } from "@phosphor-icons/react";

/**
 * FirstRunWelcomeModal — one-shot congrats overlay for the first 100
 * players. Reads profile.firstRun && !profile.hasDismissedFirstRunModal.
 * Closing (X or "Let's Play") calls POST /api/users/me/dismiss-first-run
 * so it never renders again.
 */
export default function FirstRunWelcomeModal() {
  const profile = useAuthStore((s) => s.profile);
  const patchProfile = useAuthStore((s) => s.patchProfile);
  const [dismissing, setDismissing] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(!!(profile?.firstRun && !profile?.hasDismissedFirstRunModal));
  }, [profile?.firstRun, profile?.hasDismissedFirstRunModal]);

  const dismiss = async () => {
    if (dismissing) return;
    setDismissing(true);
    // Optimistic — hide immediately even if API is slow.
    setVisible(false);
    patchProfile({ hasDismissedFirstRunModal: true });
    try {
      await api.post("/users/me/dismiss-first-run");
    } catch {
      /* non-fatal: profile is already patched locally */
    } finally {
      setDismissing(false);
    }
  };

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      data-testid="first-run-modal"
      onClick={dismiss}
    >
      <div
        className="relative w-full max-w-md rounded-2xl bg-slate-900 border border-amber-500/30 shadow-2xl ring-1 ring-black/40 p-8 text-center overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Subtle bronze radial accent behind the badge */}
        <div className="pointer-events-none absolute inset-0 opacity-40" style={{
          background: "radial-gradient(circle at 50% 25%, rgba(245,197,66,0.15), transparent 60%)"
        }} />
        <button
          type="button"
          onClick={dismiss}
          aria-label="Close"
          data-testid="first-run-modal-close-x"
          className="absolute top-3 right-3 text-slate-400 hover:text-amber-300 transition-colors rounded-full p-1.5 hover:bg-white/5"
        >
          <X size={18} weight="bold" />
        </button>

        <div className="relative flex justify-center mb-5">
          <FirstRunBadge size={72} />
        </div>

        <div className="relative">
          <div className="font-mono text-[10px] tracking-[0.3em] text-amber-400/80 mb-2 uppercase">
            Founding Member
          </div>
          <h2 className="font-display text-2xl sm:text-3xl text-white tracking-tight mb-3">
            Welcome to the First Run
          </h2>
          <p className="text-sm text-slate-300 leading-relaxed mb-4">
            Congratulations! You are one of the very first 100 players on Ace Chasers.
            To honor your status as a founding member, we&apos;ve permanently added the
            exclusive First Run disc badge to your profile.
          </p>
          <p className="text-sm text-amber-100/90 italic leading-relaxed mb-6">
            May your drives fly straight and true down the center of the fairway,
            may the trees show you mercy and grant clean gaps,
            and may every putt find the chains.
          </p>

          <button
            type="button"
            onClick={dismiss}
            disabled={dismissing}
            data-testid="first-run-modal-lets-play-btn"
            className="inline-flex items-center justify-center rounded-full bg-amber-500 hover:bg-amber-400 disabled:opacity-60 text-slate-900 font-bold text-sm px-8 py-3 transition-all duration-200 hover:scale-[1.02] active:scale-95 shadow-lg shadow-amber-500/20"
          >
            Let&apos;s Play
          </button>
        </div>
      </div>
    </div>
  );
}
