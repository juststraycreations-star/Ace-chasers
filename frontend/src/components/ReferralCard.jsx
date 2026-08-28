import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Trophy, Copy, ShareNetwork } from "@phosphor-icons/react";

/**
 * ReferralCard — a shareable invite widget shown on the Profile page.
 * Lazily mints the caller's `ref_code` via `GET /api/users/me/referral`.
 * Anyone who signs up via `?ref=CODE` gets the Founder Sponsor badge
 * and priority bag-tag placement in future leagues.
 */
export default function ReferralCard({ compact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/users/me/referral");
        setData(data);
      } catch {
        // Silent — non-critical.
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const shareUrl =
    data?.ref_code && typeof window !== "undefined"
      ? `${window.location.origin}/signup?ref=${data.ref_code}`
      : "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Referral link copied");
    } catch {
      toast.error("Copy failed");
    }
  };

  const nativeShare = async () => {
    if (!shareUrl) return;
    if (navigator.share) {
      try {
        await navigator.share({
          title: "Join me on Ace Chasers",
          text: "Sign up with my Founder Sponsor link:",
          url: shareUrl,
        });
      } catch { /* user cancelled */ }
    } else {
      copy();
    }
  };

  if (loading) return null;
  if (!data?.ref_code) return null;

  return (
    <div
      className={`rounded-2xl border ${compact ? "border-slate-200 p-4" : "border-amber-200 bg-amber-50/40 p-5"} shadow-sm`}
      data-testid="referral-card"
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
          <Trophy size={18} weight="duotone" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-amber-700">
            Founder referral
          </div>
          <div className="font-display text-lg text-slate-900">
            Invite disc-golfers you know
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Every signup via your link earns a <strong>Founder Sponsor</strong> badge and
            priority bag-tag placement in the league they join.
          </p>
          <div className="mt-3 rounded-lg bg-white border border-slate-200 p-3 text-xs font-mono-data text-slate-800 break-all" data-testid="referral-share-url">
            {shareUrl}
          </div>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={copy}
              data-testid="referral-copy-btn"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700 hover:text-slate-900 border border-slate-200 rounded-full px-3 py-1.5"
            >
              <Copy size={12} weight="duotone" /> Copy link
            </button>
            <button
              type="button"
              onClick={nativeShare}
              data-testid="referral-share-btn"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 rounded-full px-3 py-1.5"
            >
              <ShareNetwork size={12} weight="duotone" /> Share
            </button>
            <span className="ml-auto text-[10px] font-mono-data text-slate-500" data-testid="referral-count">
              {data.referred_count} referral{data.referred_count === 1 ? "" : "s"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
