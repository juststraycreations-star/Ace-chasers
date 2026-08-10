// Offline-first score sync with idempotency.
// ───────────────────────────────────────────────────────────────
// Goals:
//  1. Score entries NEVER block the UI thread — every write goes to
//     an in-memory + localStorage queue synchronously.
//  2. Each queued write gets a stable UUID idempotency key so if the
//     server sees the same write twice (retry after flaky cellular)
//     it collapses to a single DB row.
//  3. Background flush drains the queue whenever the network returns.
//
// This is deliberately dependency-free — no IndexedDB wrapper needed.
// localStorage is synchronous, fits comfortably for round-sized data,
// and survives page reloads / TWA process kills.

import api from "@/lib/api";

const STORAGE_KEY = "ace_offline_score_queue_v1";
let flushing = false;
let listenersBound = false;

function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // RFC4122-ish fallback
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function readQueue() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeQueue(q) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(q));
  } catch {
    // Storage full or unavailable — drop silently, UI still works.
  }
}

export function pendingCount() {
  return readQueue().length;
}

export function enqueueScore({ scorecardId, hole, strokes }) {
  const q = readQueue();
  // Coalesce: if we already have a pending write for the same
  // (scorecardId, hole), replace it — only the latest value matters.
  const filtered = q.filter(
    (item) => !(item.scorecardId === scorecardId && item.hole === hole)
  );
  filtered.push({
    id: uuid(),
    scorecardId,
    hole,
    strokes,
    ts: Date.now(),
  });
  writeQueue(filtered);
  // Fire-and-forget flush attempt.
  flushQueue();
}

export async function flushQueue() {
  if (flushing) return;
  if (typeof navigator !== "undefined" && navigator.onLine === false) return;
  flushing = true;
  try {
    let q = readQueue();
    while (q.length > 0) {
      const next = q[0];
      try {
        await api.patch(
          `/scorecards/${next.scorecardId}/score`,
          { hole: next.hole, strokes: next.strokes },
          { headers: { "Idempotency-Key": next.id } }
        );
        // Success — pop and persist.
        q = q.slice(1);
        writeQueue(q);
      } catch (e) {
        // Network / 5xx — stop and try again later. 4xx means the
        // server rejected the payload for a reason retrying won't
        // fix, so drop it to avoid a poison-pill loop.
        const status = e?.response?.status;
        if (status && status >= 400 && status < 500) {
          q = q.slice(1);
          writeQueue(q);
          continue;
        }
        break;
      }
    }
  } finally {
    flushing = false;
  }
}

// Auto-flush hooks — safe to call many times, no-ops after first bind.
export function bindOfflineQueueListeners() {
  if (listenersBound || typeof window === "undefined") return;
  listenersBound = true;
  window.addEventListener("online", flushQueue);
  // Periodic retry for the case where `online` never fires but
  // connectivity actually came back (common on cellular hand-off).
  setInterval(flushQueue, 15000);
  // Initial drain on load.
  flushQueue();
}
