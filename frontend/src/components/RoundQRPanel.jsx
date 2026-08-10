import { useEffect, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import api from "@/lib/api";
import { toast } from "sonner";
import { QrCode, Copy } from "@phosphor-icons/react";

/**
 * RoundQRPanel — encodes a deep-link into a scannable QR so any
 * league member (or newcomer) can point a phone camera at it and land
 * on `/rounds/{id}/checkin` which auto-enrolls them into the round.
 *
 * The QR encodes an absolute URL rooted at REACT_APP_BACKEND_URL / the
 * current origin so the target works whether the manager prints it on
 * a coffee-cup sleeve or DMs it inside the app.
 */
export default function RoundQRPanel({ roundId, roundName }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/rounds/${roundId}/qr`);
        setPayload(data);
      } catch {
        toast.error("Failed to build QR");
      } finally {
        setLoading(false);
      }
    })();
  }, [roundId]);

  const url =
    payload?.deeplink && typeof window !== "undefined"
      ? `${window.location.origin}${payload.deeplink}`
      : "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Check-in link copied");
    } catch {
      toast.error("Copy failed");
    }
  };

  return (
    <div
      className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-sm"
      data-testid="round-qr-panel"
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
          <QrCode size={18} weight="duotone" />
        </div>
        <div>
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
            Round QR check-in
          </div>
          <div className="font-display text-lg text-slate-900">
            {roundName || "Round"}
          </div>
        </div>
      </div>

      {loading && (
        <div className="text-xs text-slate-500 font-mono-data" data-testid="round-qr-loading">
          BUILDING QR…
        </div>
      )}

      {!loading && url && (
        <div className="flex flex-col sm:flex-row items-center gap-6">
          <div
            className="bg-white p-3 border border-slate-200 rounded-xl"
            data-testid="round-qr-image"
          >
            <QRCodeCanvas
              value={url}
              size={192}
              includeMargin={false}
              level="M"
              bgColor="#ffffff"
              fgColor="#0f2e1c"
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm text-slate-700 mb-3">
              Players scan this with their phone camera. If they aren&apos;t in the
              league yet we auto-add them; then we drop them straight into a
              scorecard on this round.
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs font-mono-data text-slate-700 break-all">
              {url}
            </div>
            <button
              type="button"
              onClick={copy}
              data-testid="round-qr-copy-btn"
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700 hover:text-slate-900"
            >
              <Copy size={14} weight="duotone" /> Copy link
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
