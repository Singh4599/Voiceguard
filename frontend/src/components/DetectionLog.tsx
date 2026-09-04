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
  return `${d.getHours().toString().padStart(2,"0")}:${d.getMinutes().toString().padStart(2,"0")}:${d.getSeconds().toString().padStart(2,"0")}`;
}

export default function DetectionLog({ log, stats }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [log.length]);

  const entryClass = (ev: ChunkEvent) => {
    if (ev.is_clone && ev.confidence > 0.65) return "log-entry log-ai";
    if (ev.confidence > 0.35)               return "log-entry log-medium";
    return "log-entry log-real";
  };

  const icon = (ev: ChunkEvent) => {
    if (ev.is_clone && ev.confidence > 0.65) return "🚨";
    if (ev.confidence > 0.35)               return "⚠";
    return "✓";
  };

  const label = (ev: ChunkEvent) => {
    if (ev.is_clone && ev.confidence > 0.65) return "AI Clone";
    if (ev.confidence > 0.35)               return "Suspicious";
    return "Real";
  };

  const confColor = (ev: ChunkEvent) =>
    ev.is_clone && ev.confidence > 0.65
      ? "var(--danger)"
      : ev.confidence > 0.35
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
          <div key={i} className={entryClass(ev)}>
            <span className="log-ts">{ts(ev.timestamp)}</span>
            <span className="log-chunk font-mono">#{ev.chunk.toString().padStart(3,"0")}</span>
            <span className="log-msg">{icon(ev)} {label(ev)}</span>
            <span className="log-conf font-mono" style={{ color: confColor(ev) }}>
              {Math.round(ev.confidence * 100)}%
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Stats */}
      <div className="stats-section">
        <div className="panel-title">Statistics</div>
        <div className="stats-grid">
          <div className="stat-card teal-accent">
            <div className="stat-label">Total Calls</div>
            <div className="stat-value">{stats.total}</div>
          </div>
          <div className={`stat-card ${stats.ai_detected > 0 ? "danger-accent" : "teal-accent"}`}>
            <div className="stat-label">AI Detected</div>
            <div className={`stat-value ${stats.ai_detected > 0 ? "danger" : "teal"}`}>
              {stats.ai_detected}
            </div>
          </div>
          <div className="stat-card teal-accent">
            <div className="stat-label">False Alerts</div>
            <div className="stat-value teal">{stats.false_alerts}</div>
          </div>
          <div className="stat-card amber-accent">
            <div className="stat-label">Response</div>
            <div className="stat-value">
              {(stats.avg_response_ms / 1000).toFixed(1)}
              <span style={{ fontSize: 11, color: "var(--text-2)", fontWeight: 400 }}>s</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
