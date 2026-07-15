import { useEffect, useRef, useState } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function toWsUrl(path) {
  const url = new URL(BACKEND_URL);
  const proto = url.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${url.host}${path}`;
}

export function useWebSocket(path, onMessage, enabled = true) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onMessage);
  useEffect(() => { handlerRef.current = onMessage; }, [onMessage]);

  useEffect(() => {
    if (!enabled || !path) return;
    const token = localStorage.getItem("session_token");
    if (!token) return;
    const url = toWsUrl(`${path}?token=${encodeURIComponent(token)}`);
    let ws;
    let alive = true;
    let reconnectTimer;

    const connect = () => {
      ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => alive && setConnected(true);
      ws.onclose = () => {
        if (!alive) return;
        setConnected(false);
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => {};
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

    // heartbeat
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 25000);

    return () => {
      alive = false;
      clearTimeout(reconnectTimer);
      clearInterval(heartbeat);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [path, enabled]);

  return { connected };
}
