import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Ruler, MapPin, WifiSlash, Trophy } from "@phosphor-icons/react";

/**
 * ThrowTracker — GPS-based distance measurement.
 *
 * Offline hardening (Iteration 53):
 *   • Every queued throw gets a stable uuid `idem_key` so server-side
 *     dedupe collapses double-syncs to one row.
 *   • Failures classified by status:  4xx → poison-pill drop (client-side
 *     bad payload, retrying won't fix), 5xx / network → exponential
 *     backoff scheduled per item (2^attempts · 5s, capped at 5 min).
 *   • Retry drivers: window `online` event, 15 s heartbeat interval, and
 *     the explicit "Sync now" tap in the offline badge.
 *   • flushOffline() awaits load() when ≥1 item drained so the history
 *     list refreshes without a page reload.
 */

const OFFLINE_KEY = "ace-chasers.throws.offline";
const EARTH_R_FT = 20_902_231;
const RETRY_INTERVAL_MS = 15_000;
const BASE_BACKOFF_MS = 5_000;
const MAX_BACKOFF_MS = 5 * 60 * 1000; // 5 minutes
const MAX_ATTEMPTS = 12; // after this we drop even 5xx items

function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function haversineFeet(a, b) {
  const toRad = (d) => (d * Math.PI) / 180;
  const p1 = toRad(a.lat);
  const p2 = toRad(b.lat);
  const dp = toRad(b.lat - a.lat);
  const dl = toRad(b.lon - a.lon);
  const h =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return Math.round(EARTH_R_FT * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h)) * 10) / 10;
}

function getCoords() {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("Geolocation is not supported on this device."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      (err) => reject(err),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  });
}

function readOfflineQueue() {
  try { return JSON.parse(localStorage.getItem(OFFLINE_KEY) || "[]"); } catch { return []; }
}
function writeOfflineQueue(q) {
  try { localStorage.setItem(OFFLINE_KEY, JSON.stringify(q)); } catch { /* quota — ignore */ }
}

function backoffFor(attempts) {
  return Math.min(BASE_BACKOFF_MS * 2 ** attempts, MAX_BACKOFF_MS);
}

// Migrate legacy queue entries (which had no idem_key/attempts) so they
// gain a stable idempotency key on first read. Idempotent.
function normalizeQueue(raw) {
  return raw.map((item) => ({
    idem_key: item.idem_key || uuid(),
    attempts: item.attempts || 0,
    next_attempt_at: item.next_attempt_at || 0,
    payload: item.payload || {
      start_lat: item.start_lat, start_lon: item.start_lon,
      end_lat: item.end_lat, end_lon: item.end_lon,
      client_distance_ft: item.client_distance_ft, disc: item.disc,
    },
  }));
}

export default function ThrowTracker() {
  const [start, setStart] = useState(null);
  const [busy, setBusy] = useState(false);
  const [throws, setThrows] = useState([]);
  const [pb, setPb] = useState(0);
  const [offline, setOffline] = useState(readOfflineQueue().length);
  const [disc, setDisc] = useState("");
  const flushingRef = useRef(false);

  const load = async () => {
    try {
      const { data } = await api.get("/throws", { params: { limit: 25 } });
      setThrows(data.throws || []);
      setPb(data.personal_best_ft || 0);
    } catch { /* offline — keep last render */ }
  };

  const flushOffline = async ({ silent = false } = {}) => {
    if (flushingRef.current) return 0;
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      if (!silent) toast.warning("You're offline — throws will sync automatically when reconnected.");
      return 0;
    }
    flushingRef.current = true;
    try {
      const q = normalizeQueue(readOfflineQueue());
      if (!q.length) return 0;
      const now = Date.now();
      const survivors = [];
      let ok = 0;
      let dropped = 0;
      for (const item of q) {
        // Respect scheduled backoff for this item.
        if (item.next_attempt_at && item.next_attempt_at > now && !silent) {
          survivors.push(item);
          continue;
        }
        try {
          await api.post("/throws", item.payload, {
            headers: { "Idempotency-Key": item.idem_key },
          });
          ok += 1;
        } catch (e) {
          const status = e?.response?.status;
          const attempts = item.attempts + 1;
          if (status && status >= 400 && status < 500) {
            // Poison pill — server won't ever accept this payload. Drop.
            dropped += 1;
            continue;
          }
          if (attempts >= MAX_ATTEMPTS) {
            dropped += 1;
            continue;
          }
          survivors.push({
            ...item,
            attempts,
            next_attempt_at: Date.now() + backoffFor(attempts),
          });
        }
      }
      writeOfflineQueue(survivors);
      setOffline(survivors.length);
      if (ok) {
        if (!silent) toast.success(`${ok} offline throw${ok === 1 ? "" : "s"} synced`);
        // P0 fix: refresh history so the newly-drained throws appear
        // without needing a manual page reload.
        await load();
      }
      if (dropped && !silent) {
        toast.error(`${dropped} offline throw${dropped === 1 ? " was" : "s were"} dropped (invalid or too many retries).`);
      }
      return ok;
    } finally {
      flushingRef.current = false;
    }
  };

  useEffect(() => {
    (async () => { await flushOffline({ silent: true }); await load(); })();
    const onOnline = () => flushOffline({ silent: true });
    window.addEventListener("online", onOnline);
    // Periodic retry — covers stealth reconnects where `online` never fires.
    const heartbeat = setInterval(() => flushOffline({ silent: true }), RETRY_INTERVAL_MS);
    return () => {
      window.removeEventListener("online", onOnline);
      clearInterval(heartbeat);
    };
  }, []);

  const startThrow = async () => {
    setBusy(true);
    try {
      const s = await getCoords();
      setStart(s);
      toast.success("Tee coords locked · walk to your disc");
    } catch (e) {
      toast.error(e?.message || "Could not read GPS. Enable location and try again.");
    } finally {
      setBusy(false);
    }
  };

  const markDisc = async () => {
    if (!start) { toast.error("Tap 'Start Throw' at the tee first"); return; }
    setBusy(true);
    try {
      const end = await getCoords();
      const distance_ft = haversineFeet(start, end);
      const payload = {
        start_lat: start.lat, start_lon: start.lon,
        end_lat: end.lat, end_lon: end.lon,
        client_distance_ft: distance_ft,
        disc: disc || null,
      };
      const idem_key = uuid();
      try {
        const { data } = await api.post("/throws", payload, {
          headers: { "Idempotency-Key": idem_key },
        });
        toast.success(`${data.distance_ft} ft logged`);
        setStart(null);
        await load();
      } catch {
        const q = normalizeQueue(readOfflineQueue());
        q.push({ idem_key, attempts: 0, next_attempt_at: 0, payload });
        writeOfflineQueue(q);
        setOffline(q.length);
        toast.warning(`${distance_ft} ft saved offline · will sync when you reconnect`);
        setStart(null);
      }
    } catch (e) {
      toast.error(e?.message || "Could not read GPS at the disc.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8" data-testid="throw-tracker-page">
      <div className="max-w-2xl mx-auto px-4">
        <div className="flex items-center gap-2 mb-1">
          <Ruler size={22} weight="duotone" className="text-emerald-600" />
          <h1 className="font-display text-3xl text-slate-900">Distance Throw Tracker</h1>
        </div>
        <p className="text-sm text-slate-600 mb-6">
          Tap Start Throw at the tee, walk to your disc, tap Mark Disc Position. Uses your device GPS.
        </p>

        {/* Status chips */}
        <div className="flex flex-wrap items-center gap-2 mb-6">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm">
            <Trophy size={13} weight="duotone" className="text-emerald-600" />
            PB · <span className="font-mono-data text-emerald-700">{pb} ft</span>
          </span>
          {offline > 0 && (
            <span
              data-testid="offline-badge"
              className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-200 text-amber-900 px-3 py-1.5 text-xs font-semibold"
            >
              <WifiSlash size={13} weight="duotone" />
              {offline} offline · <button className="underline" onClick={() => flushOffline()}>Sync now</button>
            </span>
          )}
        </div>

        {/* Composer */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 mb-6">
          <label className="block text-xs font-mono-data uppercase tracking-widest text-slate-500 mb-1">
            Disc (optional)
          </label>
          <input
            data-testid="throw-disc-input"
            value={disc}
            onChange={(e) => setDisc(e.target.value)}
            placeholder="Destroyer, Buzzz, etc."
            className="w-full mb-4 rounded-lg border border-slate-200 bg-slate-50/50 px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/10 focus:border-emerald-500"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              data-testid="throw-start-btn"
              onClick={startThrow}
              disabled={busy}
              className={`min-h-[56px] rounded-full font-semibold text-base transition-colors shadow-sm ${
                start
                  ? "bg-slate-100 text-slate-500 border border-slate-200"
                  : "bg-emerald-600 hover:bg-emerald-700 text-white"
              } disabled:opacity-60`}
            >
              {start ? "Tee locked ✓" : "Start Throw"}
            </button>
            <button
              data-testid="throw-mark-btn"
              onClick={markDisc}
              disabled={busy || !start}
              className="min-h-[56px] rounded-full font-semibold text-base bg-white text-slate-900 border-2 border-emerald-600 hover:bg-emerald-50 shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <MapPin size={16} weight="duotone" className="inline mr-1 text-emerald-600" />
              Mark Disc Position
            </button>
          </div>
        </div>

        {/* History */}
        <h2 className="font-display text-sm uppercase tracking-widest text-slate-700 mb-2">
          Recent throws · <span className="text-slate-400 font-mono-data">{throws.length}</span>
        </h2>
        {throws.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            No throws logged yet.
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white overflow-hidden" data-testid="throw-history">
            {throws.map((t) => (
              <li key={t.id} className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0">
                  <div className="font-mono-data text-lg text-emerald-700 font-bold">{t.distance_ft} ft</div>
                  <div className="text-[11px] text-slate-500 font-mono-data uppercase tracking-wider">
                    {new Date(t.created_at).toLocaleString()}
                    {t.disc ? ` · ${t.disc}` : ""}
                  </div>
                </div>
                {t.distance_ft === pb && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200 px-2 py-0.5 text-[10px] font-mono-data uppercase tracking-widest font-semibold">
                    <Trophy size={11} weight="fill" /> PB
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
