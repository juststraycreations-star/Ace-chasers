import { useState } from "react";
import { Link } from "react-router-dom";
import { Handshake, ShieldCheck } from "@phosphor-icons/react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * First-time onboarding overlay for a Private League Clubhouse feed.
 * Renders when the current member has not yet agreed to the Fair Play
 * Terms. Once "I Agree" is clicked, POSTs to
 *   /api/leagues/{leagueId}/clubhouse/agree
 * which persists { clubhouse_agreed: true, clubhouse_agreed_at }
 * on the league member document so this modal never renders again.
 */
export default function ClubhouseAgreementModal({ leagueId, onAgree }) {
  const [busy, setBusy] = useState(false);

  const agree = async () => {
    setBusy(true);
    try {
      await api.post(`/leagues/${leagueId}/clubhouse/agree`);
      toast.success("Welcome to the Clubhouse");
      onAgree?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not record agreement");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="clubhouse-agreement-modal"
    >
      <div className="max-w-md w-full bg-white rounded-2xl border border-gray-200 shadow-2xl overflow-hidden">
        <div className="p-6 sm:p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-11 h-11 rounded-xl bg-[#F5C542] flex items-center justify-center">
              <Handshake size={22} weight="fill" color="#0a0a0a" />
            </div>
            <div>
              <div className="font-mono-data text-[10px] text-zinc-500 tracking-wider">
                FIRST TIME · FAIR PLAY
              </div>
              <div className="font-display text-2xl tracking-tight">
                Welcome to the Clubhouse
              </div>
            </div>
          </div>
          <p className="text-sm text-gray-700 leading-relaxed">
            Welcome to the Clubhouse. By joining, you agree to our{" "}
            <Link
              to="/legal/privacy"
              data-testid="clubhouse-agreement-terms-link"
              className="text-[#F5C542] font-medium hover:underline"
            >
              Fair Play Terms
            </Link>
            , including keeping score logs transparent and maintaining respectful
            community interactions.
          </p>
          <div className="mt-5 rounded-lg bg-emerald-50 border border-emerald-200 p-3 flex items-start gap-2">
            <ShieldCheck
              size={16}
              weight="fill"
              className="text-emerald-600 flex-shrink-0 mt-0.5"
            />
            <div className="text-[11px] text-emerald-800 leading-snug">
              Your agreement is recorded on your league membership record and
              will not be requested again for this league.
            </div>
          </div>
          <button
            onClick={agree}
            disabled={busy}
            data-testid="clubhouse-agree-btn"
            className="mt-6 w-full h-11 rounded-lg bg-[#F5C542] text-black font-bold text-sm hover:bg-[#f5cf5a] transition-colors disabled:opacity-50"
          >
            {busy ? "Saving…" : "I Agree"}
          </button>
        </div>
      </div>
    </div>
  );
}
