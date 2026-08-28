import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

/**
 * LeaguesFeatureAnnouncement — pulsing amber basket icon that sits next
 * to the Leagues nav link. First click opens a compact tech-styled
 * dropdown; the CTA both navigates to /leagues and dismisses the badge.
 * Backed by POST /api/users/me/dismiss-leagues-feature.
 *
 * Renders nothing once `profile.hasViewedLeaguesFeature` is true.
 */
export default function LeaguesFeatureAnnouncement({ mobile = false }) {
  const navigate = useNavigate();
  const profile = useAuthStore((s) => s.profile);
  const patchProfile = useAuthStore((s) => s.patchProfile);
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  // Close on outside click / Escape
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!profile || profile.hasViewedLeaguesFeature) return null;

  const dismissAndGo = async () => {
    setOpen(false);
    patchProfile({ hasViewedLeaguesFeature: true });
    try {
      await api.post("/users/me/dismiss-leagues-feature");
    } catch {
      /* non-fatal */
    }
    navigate("/leagues");
  };

  const dismissOnly = async () => {
    patchProfile({ hasViewedLeaguesFeature: true });
    try {
      await api.post("/users/me/dismiss-leagues-feature");
    } catch {
      /* non-fatal */
    }
  };

  return (
    <div ref={rootRef} className={`relative ${mobile ? "" : "inline-block"}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="New feature: Leagues"
        data-testid="leagues-announcement-toggle"
        className="relative inline-flex items-center justify-center h-7 w-7 rounded-full bg-slate-900/60 hover:bg-slate-900 border border-amber-500/40 hover:border-amber-400 transition-all duration-200 hover:scale-110 active:scale-95"
      >
        {/* Pulse halo */}
        <span className="absolute inset-0 rounded-full bg-amber-500/40 animate-ping" aria-hidden="true" />
        <span className="absolute inset-0 rounded-full bg-amber-500/10" aria-hidden="true" />
        {/* Inline SVG: minimalist disc-golf basket */}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="relative h-4 w-4 text-amber-400"
          aria-hidden="true"
        >
          {/* Pole */}
          <path d="M12 3v2" />
          {/* Top rim */}
          <ellipse cx="12" cy="6" rx="6" ry="1.4" />
          {/* Chains */}
          <path d="M7 7l1.2 6M17 7l-1.2 6M10 7l0.5 6M14 7l-0.5 6" opacity="0.75" />
          {/* Basket bowl */}
          <path d="M6.4 13c0.6 2.4 2.9 3.6 5.6 3.6s5-1.2 5.6-3.6" />
          <path d="M6.5 13h11" />
          {/* Pole below */}
          <path d="M12 17v3" />
        </svg>
      </button>

      {open && (
        <div
          className={`absolute z-50 mt-2 w-80 rounded-2xl bg-slate-900 border border-amber-500/30 shadow-2xl ring-1 ring-black/40 p-5 text-left ${
            mobile ? "left-0" : "right-0"
          }`}
          data-testid="leagues-announcement-panel"
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <h3 className="font-display text-lg text-white leading-tight">
              Disc Golf Leagues Are Live! 🏆
            </h3>
            <button
              type="button"
              onClick={() => { setOpen(false); dismissOnly(); }}
              aria-label="Dismiss"
              data-testid="leagues-announcement-dismiss"
              className="-mt-1 -mr-1 text-slate-400 hover:text-amber-300 text-sm px-2 py-0.5 rounded hover:bg-white/5"
            >
              ×
            </button>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed mb-4">
            We just rolled out the ultimate companion dashboard for league management.
            Run your tags, track real-time CTP leaderboards, view live payouts, and stay
            updated on course conditions all in one place. Ready to card up?
          </p>
          <button
            type="button"
            onClick={dismissAndGo}
            data-testid="leagues-announcement-cta"
            className="w-full inline-flex items-center justify-center rounded-full bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold text-sm px-4 py-2.5 transition-all duration-200 hover:scale-[1.02] active:scale-95 shadow-lg shadow-amber-500/10"
          >
            Check Out Leagues →
          </button>
        </div>
      )}
    </div>
  );
}
