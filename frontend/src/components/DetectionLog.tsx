"use client";
import { useEffect, useRef } from "react";
import { ChunkEvent } from "@/hooks/useBackendWS";

interface Stats {
  total: number;
  ai_detected: number;
  false_alerts: number;
  avg_response_ms: number;
}
interface Props { log: ChunkEvent[]; stats: Stats; }

function ts(iso: string): string {
  const d = new Date(iso);
  return `[${d.getMinutes().toString()}:${d.getSeconds().toString().padStart(2,"0")}.${d.getMilliseconds().toString().padStart(3,"0")}]`;
}

export default function DetectionLog({ log, stats }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [log.length]);

  const entryClass = (ev: ChunkEvent) => {
    if (ev.confidence > 0.45) return "log-entry log-ai";
    if (ev.confidence > 0.25) return "log-entry log-medium";
    return "log-entry log-real";
  };

  const icon = (ev: ChunkEvent) => {
    if (ev.confidence > 0.45) return "😠";
    if (ev.confidence > 0.25) return "😐";
    return "🙂";
  };

  const label = (ev: ChunkEvent) => {
    return "Confidence";
  };

  const confColor = (ev: ChunkEvent) =>
    ev.confidence > 0.45
      ? "var(--danger)"
      : ev.confidence > 0.25
      ? "var(--amber)"
      : "var(--teal)";

  return (
    <div className="panel log-panel">
      <div className="panel-header">
        <span className="panel-title">Detection Log</span>
        <span className="font-mono" style={{ fontSize: 9, color: "var(--text-3)" }}>
          {log.length} events
        </span>
      </div>

      <div className="log-feed panel-body">
        {log.length === 0 && (
          <div className="font-mono" style={{ color: "var(--text-3)", fontSize: 10, padding: "12px 8px" }}>
            Waiting for events…
          </div>
        )}
        {log.map((ev, i) => (
          <div key={i} className={entryClass(ev)} style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-2)' }}>
            <span className="log-ts">{ts(ev.timestamp)}</span>
            <span className="log-chunk"> chunk {ev.chunk}: </span>
            <span className="log-msg" style={{ marginLeft: '8px' }}>{icon(ev)} {label(ev)}</span>
            <span className="log-conf" style={{ color: 'var(--text-1)', marginLeft: '4px' }}>
              {Math.round(ev.confidence * 100)}%
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
