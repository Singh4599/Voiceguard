"use client";
import { CallInfo, ChunkEvent } from "@/hooks/useBackendWS";
import Oscilloscope from "./Oscilloscope";

interface Props { call: CallInfo | null; }

function chunkClass(ev: ChunkEvent, isLatest: boolean): string {
  let base = "chunk-block";
  if (ev.is_clone && ev.confidence > 0.6) base += " ai";
  else if (ev.confidence > 0.35) base += " medium";
  else base += " real";
  if (isLatest) base += " latest";
  return base;
}

function confClass(confidence: number): string {
  if (confidence > 0.65) return "conf-value conf-high";
  if (confidence > 0.35) return "conf-value conf-medium";
  return "conf-value conf-real";
}

function barClass(confidence: number): string {
  if (confidence > 0.65) return "bar-fill high";
  if (confidence > 0.35) return "bar-fill medium";
  return "bar-fill real";
}

export default function CallAnalysis({ call }: Props) {
  if (!call) {
    return (
      <div className="panel" style={{ borderRight: "1px solid var(--border)" }}>
        <div className="no-call">
          <span className="no-call-icon">🎙️</span>
          <span className="no-call-text">Select a call to analyse</span>
        </div>
      </div>
    );
  }

  const latest = call.chunks[call.chunks.length - 1];
  const conf = latest?.confidence ?? 0;
  const confPct = Math.round(conf * 100);
  const isAI = latest?.is_clone && conf > 0.65;
  const isMed = conf > 0.35 && conf <= 0.65;

  return (
    <div className="panel" style={{ borderRight: "1px solid var(--border)" }}>
      <div className="panel-header">
        <span className="panel-title">Call Analysis</span>
        <span className="font-mono" style={{ fontSize: 9, color: "var(--text-3)" }}>
          {call.active ? "● LIVE" : "○ ENDED"}
        </span>
      </div>

      <div className="analysis-panel">
        {/* Call ID */}
        <div className="call-id-row">
          <span className="call-id-label">CALL ID</span>
          <span className="call-id-value font-mono">{call.call_id.slice(0, 8)}…{call.call_id.slice(-6)}</span>
          {isAI && (
            <span className="call-badge badge-high" style={{ marginLeft: "auto" }}>
              🚨 AI CLONE
            </span>
          )}
        </div>

        {/* Oscilloscope */}
        <div>
          <div className="section-label">Waveform</div>
          <div className="oscilloscope-wrap">
            <Oscilloscope chunks={call.chunks} active={call.active} />
          </div>
        </div>

        {/* Chunk Timeline */}
        <div>
          <div className="section-label" style={{ marginBottom: 10 }}>
            Chunk Timeline
            <span className="font-mono" style={{ color: "var(--text-3)", marginLeft: 8 }}>
              (2s each · {call.chunks.length} total)
            </span>
          </div>
          <div className="chunk-timeline">
            {call.chunks.map((ev, i) => (
              <div
                key={i}
                className={chunkClass(ev, i === call.chunks.length - 1)}
                title={`Chunk ${ev.chunk} · ${Math.round(ev.confidence * 100)}% AI`}
              />
            ))}
          </div>
        </div>

        {/* Confidence Bar */}
        <div className="confidence-bar-wrap">
          <div className="confidence-labels">
            <span className="conf-label">AI Clone Probability</span>
            <span className={confClass(conf)}>
              {confPct}%
              {isAI ? " — AI CLONE" : isMed ? " — SUSPICIOUS" : " — REAL VOICE"}
            </span>
          </div>
          <div className="bar-track">
            <div
              className={barClass(conf)}
              style={{ width: `${confPct}%` }}
            />
          </div>
        </div>

        {/* Indicators */}
        {latest?.indicators && latest.indicators.length > 0 && (
          <div>
            <div className="section-label">Detection Signals</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {latest.indicators.map((ind, i) => (
                <div
                  key={i}
                  className="font-mono"
                  style={{
                    fontSize: 10,
                    color: isAI ? "var(--danger)" : "var(--text-2)",
                    padding: "4px 8px",
                    background: isAI ? "var(--danger-dim)" : "var(--bg-card)",
                    border: `1px solid ${isAI ? "var(--danger)" : "var(--border)"}`,
                    borderRadius: 4,
                  }}
                >
                  → {ind}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
