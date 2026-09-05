"use client";
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
  if (!call) {
    return (
      <div className="panel" style={{ borderRight: "1px solid var(--border)" }}>
        <div className="panel-header">
          <span className="panel-title">Call Analysis</span>
        </div>
        <div className="no-call">
          <span className="no-call-icon">🎙️</span>
          <span className="no-call-text">Select a call to analyse</span>
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
        <div className="call-id-row" style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span className="call-id-label" style={{ fontSize: '14px', letterSpacing: '0.1em' }}>CALL ID:</span>
          <span className="call-id-value font-mono" style={{ fontSize: '16px', color: 'var(--text-2)' }}>
            {call.call_id}
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
            CHUNK TIMELINE <span style={{ color: "var(--text-3)", textTransform: "none" }}>(2 seconds)</span>
          </div>
          <div className="chunk-timeline" style={{ marginTop: '12px' }}>
            {call.chunks.map((ev, i) => (
              <div
                key={i}
                className={chunkClass(ev, i === call.chunks.length - 1)}
                title={`#${ev.chunk} — ${Math.round(ev.confidence * 100)}% AI`}
              />
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-3)' }}>
            {[...Array(21)].map((_, i) => <span key={i}>{i}s</span>)}
          </div>
        </div>

        {/* Confidence Bar */}
        <div className="confidence-bar-wrap" style={{ marginTop: '24px' }}>
          <div className="section-label">
            CONFIDENCE <span style={{ color: "var(--text-3)", textTransform: "none" }}>(2 seconds)</span>
          </div>
          <div style={{ color: "var(--text-2)", fontSize: '11px', marginBottom: '16px' }}>AI Probability</div>
          
          <div className="bar-track">
            <div className={barClass} style={{ width: `${confPct}%`, position: 'relative' }}>
              <span style={{ position: 'absolute', right: '-10px', top: '-24px', fontSize: '12px', fontWeight: 600, color: 'inherit' }}>{confPct}%</span>
              <div style={{ position: 'absolute', right: 0, top: '-4px', bottom: '-4px', width: '2px', background: 'inherit' }}></div>
            </div>
          </div>
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
