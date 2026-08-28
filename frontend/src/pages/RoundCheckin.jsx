import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

/**
 * RoundCheckin — landing page hit after a player scans the round QR.
 * POSTs to `/rounds/{id}/self-enroll` which:
 *   - Auto-joins the league if the user isn't a member yet
 *   - Creates or reuses a solo card + scorecard on the round
 * Redirects into the live scorecard on success.
 */
export default function RoundCheckin() {
  const { roundId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [status, setStatus] = useState("enrolling"); // enrolling | done | error
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!user) {
      // User must be signed in — bounce to login with return-to.
      navigate(`/login?next=/rounds/${roundId}/checkin`);
      return;
    }
    (async () => {
      try {
        const { data } = await api.post(`/rounds/${roundId}/self-enroll`);
        setDetail(data);
        setStatus("done");
        toast.success(
          data.already_enrolled
            ? "You're already on this round"
            : "Checked in · card ready"
        );
        setTimeout(() => navigate(`/rounds/${roundId}`), 900);
      } catch (e) {
        setStatus("error");
        setDetail({ error: e?.response?.data?.detail || "Check-in failed" });
      }
    })();
  }, [roundId, user, navigate]);

  return (
    <div
      className="min-h-screen bg-slate-50 flex items-center justify-center p-6"
      data-testid="round-checkin-page"
    >
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8 max-w-md w-full text-center">
        {status === "enrolling" && (
          <>
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500 mb-2">
              Round check-in
            </div>
            <div className="font-display text-2xl text-slate-900 mb-2">
              Enrolling you…
            </div>
            <div className="text-sm text-slate-600">Hold tight.</div>
          </>
        )}
        {status === "done" && (
          <>
            <CheckCircle size={48} weight="duotone" className="text-emerald-600 mx-auto mb-3" />
            <div className="font-display text-2xl text-slate-900 mb-1">
              {detail?.already_enrolled ? "Already checked in" : "You're in"}
            </div>
            <div className="text-sm text-slate-600">
              {detail?.auto_joined_league
                ? "We added you to the league and put you on a card."
                : "Taking you to your scorecard…"}
            </div>
          </>
        )}
        {status === "error" && (
          <>
            <WarningCircle size={48} weight="duotone" className="text-red-500 mx-auto mb-3" />
            <div className="font-display text-2xl text-slate-900 mb-1">
              Couldn&apos;t check you in
            </div>
            <div className="text-sm text-slate-600" data-testid="round-checkin-error">
              {detail?.error}
            </div>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-4 text-xs font-semibold text-slate-700 hover:text-slate-900"
            >
              Try again
            </button>
          </>
        )}
      </div>
    </div>
  );
}
