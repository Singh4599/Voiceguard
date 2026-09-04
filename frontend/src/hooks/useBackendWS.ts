"use client";
import { useEffect, useRef, useState, useCallback } from "react";

export interface ChunkEvent {
  call_id: string;
  chunk: number;
  is_clone: boolean;
  confidence: number;   // 0–1, AI probability
  risk: "low" | "medium" | "high";
  indicators: string[];
  timestamp: string;    // ISO
}

export interface CallInfo {
  call_id: string;
  phone?: string;
  started_at: string;
  chunks: ChunkEvent[];
  latest_risk: "low" | "medium" | "high";
  latest_confidence: number;
  active: boolean;
}

interface State {
  calls: Record<string, CallInfo>;
  stats: { total: number; ai_detected: number; false_alerts: number; avg_response_ms: number };
  connected: boolean;
}

const BACKEND_WS =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_BACKEND_URL
      ? process.env.NEXT_PUBLIC_BACKEND_URL.replace(/^http/, "ws") + "/ws/dashboard"
      : `ws://${window.location.hostname}:8000/ws/dashboard`
    : "ws://localhost:8000/ws/dashboard";

export function useBackendWS() {
  const [state, setState] = useState<State>({
    calls: {},
    stats: { total: 0, ai_detected: 0, false_alerts: 0, avg_response_ms: 1800 },
    connected: false,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(BACKEND_WS);
    wsRef.current = ws;

    ws.onopen = () => {
      setState((s) => ({ ...s, connected: true }));
    };

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false }));
      reconnectTimer.current = setTimeout(connect, 2500);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string);

        if (msg.type === "chunk") {
          const ev: ChunkEvent = msg.data;
          setState((s) => {
            const prev = s.calls[ev.call_id];
            const updated: CallInfo = prev
              ? {
                  ...prev,
                  chunks: [...prev.chunks, ev].slice(-60),
                  latest_risk: ev.risk,
                  latest_confidence: ev.confidence,
                  active: true,
                }
              : {
                  call_id: ev.call_id,
                  started_at: ev.timestamp,
                  chunks: [ev],
                  latest_risk: ev.risk,
                  latest_confidence: ev.confidence,
                  active: true,
                };

            const ai_detected = Object.values({ ...s.calls, [ev.call_id]: updated }).filter(
              (c) => c.chunks.some((ch) => ch.is_clone)
            ).length;

            return {
              ...s,
              calls: { ...s.calls, [ev.call_id]: updated },
              stats: { ...s.stats, total: Object.keys(s.calls).length + 1, ai_detected },
            };
          });
        }

        if (msg.type === "call_end") {
          setState((s) => ({
            ...s,
            calls: {
              ...s.calls,
              [msg.call_id]: { ...s.calls[msg.call_id], active: false },
            },
          }));
        }

        if (msg.type === "stats") {
          setState((s) => ({ ...s, stats: { ...s.stats, ...msg.data } }));
        }
      } catch { /* ignore parse errors */ }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return state;
}
