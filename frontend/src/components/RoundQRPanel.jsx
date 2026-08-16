import { useCallback, useEffect, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import api from "@/lib/api";
import { toast } from "sonner";
import { QrCode, Copy, ArrowsClockwise } from "@phosphor-icons/react";
import { useWebSocket } from "@/lib/ws";

/**
 * RoundQRPanel — encodes a deep-link into a scannable QR so any
 * league member (or newcomer) can point a phone camera at it and land
 * on `/rounds/{id}/checkin` which auto-enrolls them into the round.
 *
 * Two extras beyond the QR itself:
 *   1. A manual join-code fallback (Iteration 63) shown beneath the QR
 *      for players who can't scan (glare, dead camera, etc.).
 *   2. A director-only 1-tap "Regenerate" refresh button (Iteration 65)
 *      that mints a fresh 4-char code and broadcasts it over the
 *      `round:{id}` and `league:{id}` WS channels so every subscribed
 *      manager screen refreshes without a page reload.
 */
export default function RoundQRPanel({ roundId, roundName, isDirector = false }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rotating, setRotating] = useState(false);

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

  // Live-refresh the display when ANY director rotates the code — even
  // from a different device — via the round-scoped WS channel.
  const onWsMessage = useCallback((msg) => {
    if (!msg || msg.type !== "join_code_rotated") return;
    if (msg.round_id !== roundId) return;
    setPayload((prev) => (prev ? { ...prev, join_code: msg.join_code } : prev));
  }, [roundId]);
  useWebSocket(`/api/ws/rounds/${roundId}`, onWsMessage, Boolean(roundId));

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

  const regenerate = async () => {
    if (rotating) return;
    setRotating(true);
    try {
      const { data } = await api.put(`/rounds/${roundId}/regenerate-code`);
      // Optimistic local update — the WS broadcast will follow, but
      // the caller's screen shouldn't wait for their own echo.
      setPayload((prev) => (prev ? { ...prev, join_code: data.join_code } : prev));
      toast.success(`New code · ${data.join_code}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not regenerate code");
    } finally {
      setRotating(false);
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

      {/* Manual join-code fallback — for players dealing with camera
          glare or hardware scanning failures on the course. */}
      {!loading && payload?.join_code && (
        <div className="mt-6 pt-6 border-t border-slate-100">
          <div
            className="text-xs font-bold text-gray-400 tracking-wider mb-1"
            data-testid="round-qr-join-label"
          >
            OR ENTER MANUAL JOIN CODE
          </div>
          <div className="inline-flex items-center gap-2">
            <div
              data-testid="round-qr-join-code"
              className="text-2xl font-mono font-bold tracking-widest text-emerald-700 bg-gray-50 px-4 py-2 rounded-lg border border-gray-200 inline-block"
            >
              {payload.join_code
                .toString()
                .toUpperCase()
                .split("")
                .join(" ")}
            </div>
            {isDirector && (
              <button
                type="button"
                onClick={regenerate}
                disabled={rotating}
                title="Regenerate Join Code"
                aria-label="Regenerate Join Code"
                data-testid="round-qr-regenerate-btn"
                className="p-2 text-gray-400 hover:text-emerald-600 transition-colors disabled:opacity-50"
              >
                <ArrowsClockwise
                  size={18}
                  weight="bold"
                  className={rotating ? "animate-spin" : ""}
                />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
