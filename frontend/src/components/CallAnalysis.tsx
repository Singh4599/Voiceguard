"use client";
import { useState } from "react";
import { CallInfo, ChunkEvent } from "@/hooks/useBackendWS";
import Oscilloscope from "./Oscilloscope";

interface Props {
  call: CallInfo | null;
  isAlerted: boolean;
}

function chunkClass(ev: ChunkEvent, isLatest: boolean): string {
  let c = "chunk-block";
  if      (ev.confidence > 0.45) c += " ai";
  else if (ev.confidence > 0.25) c += " medium";
  else                           c += " real";
  if (isLatest) c += " latest";
  return c;
}

export default function CallAnalysis({ call, isAlerted }: Props) {
  const [simulating, setSimulating] = useState(false);

  const handleSimulate = async () => {
    setSimulating(true);
    try {
      await fetch("http://localhost:8000/api/simulate", { method: "POST" });
      setTimeout(() => setSimulating(false), 2000);
    } catch (e) {
      console.error(e);
      setSimulating(false);
    }
  };

  if (!call) {
    return (
      <div className="panel" style={{ borderRight: "1px solid var(--border)" }}>
        <div className="panel-header">
          <span className="panel-title">Call Analysis</span>
        </div>
        <div className="radar-container">
          <div className="radar">
            <div className="radar-sweep"></div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
            <span className="empty-title">Scanning Frequencies</span>
            <span className="empty-subtitle">Waiting to intercept and analyze live Exotel audio streams.</span>
          </div>
          <button 
            className="simulate-btn" 
            onClick={handleSimulate} 
            disabled={simulating}
          >
            {simulating ? "INJECTING SIGNAL..." : "SIMULATE DEMO CALL"}
          </button>
        </div>
      </div>
    );
  }

  const latest  = call.chunks[call.chunks.length - 1];
  const conf    = latest?.confidence ?? 0;
  const confPct = Math.round(conf * 100);
  const isAI    = conf > 0.45;
  const isMed   = conf > 0.25 && conf <= 0.45;

  const confClass = isAI ? "conf-value conf-high" : isMed ? "conf-value conf-medium" : "conf-value conf-real";
  const barClass  = isAI ? "bar-fill high"        : isMed ? "bar-fill medium"        : "bar-fill real";
  const statusLabel = isAI ? "AI CLONE DETECTED" : isMed ? "SUSPICIOUS" : "REAL VOICE";

  return (
    <div className="panel" style={{ borderRight: "1px solid var(--border)" }}>
      <div className="panel-header">
        <span className="panel-title">Call Analysis</span>
        <span className="font-mono" style={{ fontSize: 9, color: call.active ? "var(--teal)" : "var(--text-3)" }}>
          {call.active ? "● LIVE" : "○ ENDED"}
        </span>
      </div>

      <div className="analysis-panel">
        {/* Prevention Banner */}
        {isAlerted && (
          <div className="prevention-banner">
            <span className="icon">🛡️</span>
            PREVENTION ACTIVATED — SMS Alert Sent to Recipient
          </div>
        )}

        {/* Call ID */}
        <div className="call-id-row">
          <span className="call-id-label">CALL ID</span>
          <span className="call-id-value font-mono">
            {call.call_id.slice(0, 8)}…{call.call_id.slice(-6)}
          </span>
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
          <div className="section-label">
            Chunk Timeline
            <span style={{ fontWeight: 400, fontSize: 8, color: "var(--text-3)", letterSpacing: "0.06em" }}>
              2s · {call.chunks.length} chunks
            </span>
          </div>
          <div className="chunk-timeline">
            {call.chunks.map((ev, i) => (
              <div
                key={i}
                className={chunkClass(ev, i === call.chunks.length - 1)}
                title={`#${ev.chunk} — ${Math.round(ev.confidence * 100)}% AI`}
              />
            ))}
          </div>
        </div>

        {/* Confidence Bar */}
        <div className="confidence-bar-wrap">
          <div className="confidence-labels">
            <span className="conf-label">AI Probability</span>
            <span className={confClass}>{confPct}%</span>
          </div>
          <div className="bar-track">
            <div className={barClass} style={{ width: `${confPct}%` }} />
          </div>
          <div className="bar-sublabel">{statusLabel}</div>
        </div>

        {/* Detection Indicators */}
        {latest?.indicators && latest.indicators.length > 0 && (
          <div>
            <div className="section-label">Detection Signals</div>
            <div className="indicator-list">
              {latest.indicators.map((ind, i) => (
                <div key={i} className={`indicator-item ${isAI ? "ai" : "real"}`}>
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
