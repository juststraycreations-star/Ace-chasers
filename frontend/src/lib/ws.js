import { useEffect, useRef, useState } from "react";
import { firebaseConfigured, getFirebaseAuth } from "./firebase";

// Resolve the backend host the same way api.js does. When the page is
// served from any *.acechasers.net origin, WebSocket URLs are built off
// window.location so they hit the same domain (avoids cross-origin WS
// upgrades that Cloudflare rejects). Falls back to the build-time env
// var everywhere else (preview, localhost, mobile TWA shell, etc.).
function resolveWsBase() {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host.endsWith('acechasers.net')) {
      return window.location.origin;
    }
  }
  const fromEnv = process.env.REACT_APP_BACKEND_URL;
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined') return window.location.origin;
  return '';
}

function toWsUrl(path) {
  const base = resolveWsBase();
  if (!base) throw new Error('No backend base URL');
  const url = new URL(base);
  const proto = url.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${url.host}${path}`;
}

/**
 * Return a fresh auth token (Firebase ID token, or the dev JWT when
 * Firebase isn't configured). Returns `null` when the user isn't signed
 * in — callers should NOT open a socket in that case.
 */
async function currentAuthToken() {
  if (firebaseConfigured) {
    try {
      const auth = getFirebaseAuth();
      const user = auth?.currentUser;
      if (!user) return null;
      return await user.getIdToken();
    } catch {
      return null;
    }
  }
  return localStorage.getItem("ace_dev_token") || null;
}

/**
 * useWebSocket — auto-reconnecting socket for realtime round updates.
 *
 * Feb 2026 hardening:
 *  - Reads the CURRENT Firebase ID token via getIdToken() instead of a
 *    stale `session_token` localStorage key that was never set → fixes
 *    the "RECONNECTING…" that appears forever on scorecards.
 *  - Skips reconnect entirely when there's no user (no more 3s spam).
 *  - Cleans up more aggressively so navigating away from a round
 *    doesn't leave a dangling socket that stalls back-button loads.
 *  - Exponential-ish backoff (3s → 6s → 12s, capped) so a wedged
 *    origin doesn't hammer the server.
 */
export function useWebSocket(path, onMessage, enabled = true) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onMessage);
  useEffect(() => { handlerRef.current = onMessage; }, [onMessage]);

  useEffect(() => {
    if (!enabled || !path) return undefined;

    let ws;
    let alive = true;
    let reconnectTimer;
    let heartbeat;
    let backoffMs = 3000;

    const connect = async () => {
      if (!alive) return;
      const token = await currentAuthToken();
      if (!alive) return;
      if (!token) {
        // Nothing to auth with — surface as disconnected and try once
        // more later. If the user just isn't logged in this is harmless
        // because RoundScorecard is a protected route anyway.
        setConnected(false);
        reconnectTimer = setTimeout(connect, 5000);
        return;
      }

      let url;
      try {
        url = toWsUrl(`${path}?token=${encodeURIComponent(token)}`);
      } catch (err) {
        // Malformed backend URL — no point retrying.
        console.error("useWebSocket: bad URL", err);
        setConnected(false);
        return;
      }

      try {
        ws = new WebSocket(url);
      } catch (err) {
        setConnected(false);
        reconnectTimer = setTimeout(connect, backoffMs);
        backoffMs = Math.min(backoffMs * 2, 30000);
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        if (!alive) return;
        setConnected(true);
        backoffMs = 3000; // reset backoff on any successful open
      };
      ws.onclose = () => {
        if (!alive) return;
        setConnected(false);
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connect, backoffMs);
        backoffMs = Math.min(backoffMs * 2, 30000);
      };
      ws.onerror = () => { /* onclose fires next; single reconnect path */ };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          handlerRef.current?.(msg);
        } catch {
          // ignore non-JSON (pong)
        }
      };
    };

    connect();

    heartbeat = setInterval(() => {
      try {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send("ping");
        }
      } catch { /* non-fatal */ }
    }, 25000);

    return () => {
      alive = false;
      clearTimeout(reconnectTimer);
      clearInterval(heartbeat);
      const s = wsRef.current;
      if (s) {
        // Detach handlers BEFORE calling close so onclose doesn't fire a
        // reconnect during teardown — that was leaving zombie sockets
        // that stalled back-button navigation.
        try { s.onopen = null; s.onclose = null; s.onerror = null; s.onmessage = null; } catch { /* noop */ }
        try {
          if (s.readyState === WebSocket.OPEN || s.readyState === WebSocket.CONNECTING) {
            s.close(1000, "unmount");
          }
        } catch { /* noop */ }
        wsRef.current = null;
      }
    };
  }, [path, enabled]);

  return { connected };
}
