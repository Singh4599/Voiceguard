"use client";
import { useEffect, useRef, useState } from "react";
import { CallInfo } from "@/hooks/useBackendWS";
import MiniWaveform from "./MiniWaveform";

interface Props {
  calls: Record<string, CallInfo>;
  selectedId: string | null;
  alertedCalls: Set<string>;
  onSelect: (id: string) => void;
}

function formatDuration(isoStart: string): string {
  const diff = Math.max(0, Math.floor((Date.now() - new Date(isoStart).getTime()) / 1000));
  const m = Math.floor(diff / 60).toString().padStart(2, "0");
  const s = (diff % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function maskPhone(callId: string): string {
  const d = callId.replace(/\D/g, "").slice(-10);
  if (d.length >= 10) return `+91 ${d.slice(0, 2)}XX ${d.slice(4, 6)}XX ${d.slice(8)}`;
  return "+91 98XX XXXX";
}

export default function ActiveCallsList({ calls, selectedId, alertedCalls, onSelect }: Props) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const sorted = Object.values(calls).sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1;
    return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
  });

  const hasClone = (c: CallInfo) => c.chunks.some((ch) => ch.is_clone && ch.confidence > 0.5);

  const cardClass = (c: CallInfo) => {
    let cls = "call-card";
    if (selectedId === c.call_id) cls += " active";
    else if (hasClone(c) && c.latest_risk === "high")   cls += " risk-high";
    else if (c.latest_risk === "medium") cls += " risk-medium";
    return cls;
  };

  const badgeLabel = (c: CallInfo) => {
    if (!hasClone(c)) return "REAL";
    if (c.latest_risk === "high")   return "AI CLONE";
    if (c.latest_risk === "medium") return "SUSPICIOUS";
    return "CLEAR";
  };

  const badgeClass = (c: CallInfo) => {
    if (!hasClone(c)) return "call-badge badge-safe";
    if (c.latest_risk === "high")   return "call-badge badge-high";
    if (c.latest_risk === "medium") return "call-badge badge-medium";
    return "call-badge badge-safe";
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Active Calls</span>
        <span className="font-mono" style={{ fontSize: 10, color: "var(--text-3)" }}>
          {sorted.filter((c) => c.active).length} live
        </span>
      </div>

      <div className="panel-body">
        {sorted.length === 0 ? (
          <div className="no-call" style={{ marginTop: 60 }}>
            <span className="no-call-icon">📞</span>
            <span className="no-call-text">Waiting for calls…</span>
          </div>
        ) : (
          <div className="call-list">
            {sorted.map((c) => (
              <div key={c.call_id} className={cardClass(c)} onClick={() => onSelect(c.call_id)} style={{ position: 'relative', overflow: 'hidden' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span className="call-number" style={{ fontSize: '15px', color: 'var(--text-1)' }}>{maskPhone(c.call_id)}</span>
                    <span className="font-mono" style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                      {formatDuration(c.started_at)}
                    </span>
                  </div>
                  <span className={badgeClass(c)}>{badgeLabel(c)}</span>
                </div>
                <div style={{ marginTop: '16px', margin: '0 -24px -24px -24px' }}>
                  <MiniWaveform active={c.active} risk={hasClone(c) ? c.latest_risk : "low"} />
                </div>
                {alertedCalls.has(c.call_id) && (
                  <div className="prevention-stamp">🛡 PREVENTION ACTIVATED</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
