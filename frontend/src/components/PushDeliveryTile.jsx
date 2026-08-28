import { useEffect, useState } from "react";
import api from "@/lib/api";
import { BellRinging, WarningCircle, CheckCircle, Broom } from "@phosphor-icons/react";

// Human labels for event_type strings that ship from push_service.
// Keep in sync with `_build_payload` on the backend.
const EVENT_LABEL = {
  join_code_rotated: "Join Code Rotated",
  payouts_finalized: "Payout Finalize",
  bracket_advance: "Bracket Advance",
};

function relTime(iso) {
  if (!iso) return "just now";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "just now";
  const secs = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

/**
 * PushDeliveryTile — observability panel for the FCM fan-out worker.
 *
 * Reads `/api/push/log` (Iteration 72) and renders:
 *   • A three-cell metric grid (Delivered / Failed / Broadcast Events).
 *   • A flat, plain-text chronological list of the last 5 events using
 *     the sentence template:
 *       "<Event Label>: N delivered, M failed, K pruned (T ago)."
 *
 * Polls every 30 s so a dashboard left open stays fresh without a
 * WebSocket subscription.
 */
export default function PushDeliveryTile() {
  const [totals, setTotals] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get("/push/log", { params: { limit: 25 } });
        if (cancelled) return;
        setTotals(data.totals || { sent: 0, failed: 0, pruned: 0, count: 0 });
        setRows((data.rows || []).slice(0, 5));
      } catch {
        // Endpoint may not exist yet on legacy backends — panel stays quiet.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  if (loading) return null;

  return (
    <section
      data-testid="push-delivery-tile"
      className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm mb-6"
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center">
          <BellRinging size={18} weight="duotone" />
        </div>
        <div>
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-emerald-700">
            Push Delivery
          </div>
          <div className="font-display text-base text-slate-900">
            FCM fan-out health
          </div>
        </div>
      </div>

      {/* Numerical grid */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono-data text-slate-500 mb-1 flex items-center gap-1">
            <CheckCircle size={11} weight="duotone" /> Delivered
          </div>
          <div
            className="text-sm font-medium text-emerald-700"
            data-testid="push-tile-delivered"
          >
            {totals?.sent ?? 0}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono-data text-slate-500 mb-1 flex items-center gap-1">
            <WarningCircle size={11} weight="duotone" /> Failed
          </div>
          <div
            className="text-sm font-medium text-amber-600"
            data-testid="push-tile-failed"
          >
            {totals?.failed ?? 0}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono-data text-slate-500 mb-1 flex items-center gap-1">
            <Broom size={11} weight="duotone" /> Broadcast Events Checked
          </div>
          <div
            className="text-sm font-medium text-emerald-700"
            data-testid="push-tile-events"
          >
            {totals?.count ?? 0}
          </div>
        </div>
      </div>

      {/* Live Activity Status List — last 5 events as flat sentences */}
      <div>
        <div className="text-[10px] uppercase tracking-widest font-mono-data text-slate-500 mb-2">
          Live Activity Status
        </div>
        {rows.length === 0 ? (
          <div className="text-sm text-slate-500" data-testid="push-tile-activity-empty">
            No broadcast events logged yet.
          </div>
        ) : (
          <ul className="space-y-1" data-testid="push-tile-activity-list">
            {rows.map((r) => {
              const label = EVENT_LABEL[r.eventType] || r.eventType || "Event";
              return (
                <li
                  key={r.id}
                  data-testid={`push-tile-activity-row-${r.id}`}
                  className="text-sm text-slate-700 font-mono-data leading-relaxed"
                >
                  {label}: {r.totalSent ?? 0} delivered, {r.totalFailed ?? 0} failed,{" "}
                  {r.tokensPruned ?? 0} pruned ({relTime(r.timestamp)}).
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
