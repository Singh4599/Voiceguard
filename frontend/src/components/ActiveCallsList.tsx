"use client";
import { useEffect, useRef, useState } from "react";
import { CallInfo } from "@/hooks/useBackendWS";
import MiniWaveform from "./MiniWaveform";

interface Props {
  calls: Record<string, CallInfo>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function formatDuration(isoStart: string): string {
  const diff = Math.floor((Date.now() - new Date(isoStart).getTime()) / 1000);
  const m = Math.floor(diff / 60).toString().padStart(2, "0");
  const s = (diff % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function maskNumber(callId: string): string {
  // Use last 10 digits of call_id as a pseudo phone number
  const digits = callId.replace(/\D/g, "").slice(-10);
  if (digits.length >= 10)
    return `+91 ${digits.slice(0, 2)}XX ${digits.slice(4, 6)}XX ${digits.slice(8)}`;
  return `+91 98XX XXXX`;
}

export default function ActiveCallsList({ calls, selectedId, onSelect }: Props) {
  const [, tick] = useState(0);

  // Re-render every second to update durations
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const sorted = Object.values(calls).sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1;
    return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
  });

  const badgeClass = (risk: string) =>
    risk === "high" ? "call-badge badge-high" :
    risk === "medium" ? "call-badge badge-medium" :
    "call-badge badge-safe";

  const badgeLabel = (risk: string, isClone: boolean) => {
    if (!isClone) return "REAL";
    return risk === "high" ? "AI CLONE" : risk === "medium" ? "SUSPICIOUS" : "CLEAR";
  };

  const cardClass = (call: CallInfo) => {
    const base = "call-card";
    const active = selectedId === call.call_id ? " active" : "";
    const risk =
      call.latest_risk === "high" && call.chunks.some((c) => c.is_clone) ? " risk-high" :
      call.latest_risk === "medium" ? " risk-medium" : "";
    return base + active + risk;
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
            <span className="no-call-text">Waiting for calls...</span>
          </div>
        ) : (
          <div className="call-list">
            {sorted.map((call) => {
              const hasClone = call.chunks.some((c) => c.is_clone);
              return (
                <div
                  key={call.call_id}
                  className={cardClass(call)}
                  onClick={() => onSelect(call.call_id)}
                >
                  <div className="call-card-top">
                    <span className="call-number">{maskNumber(call.call_id)}</span>
                    <span className={badgeClass(hasClone ? call.latest_risk : "low")}>
                      {badgeLabel(call.latest_risk, hasClone)}
                    </span>
                  </div>
                  <div className="call-meta">
                    <span className="call-duration">
                      {call.active ? "⬤ " : "○ "}
                      {formatDuration(call.started_at)}
                    </span>
                    <span className="font-mono" style={{ fontSize: 9, color: "var(--text-3)" }}>
                      {call.chunks.length} chunks
                    </span>
                  </div>
                  <MiniWaveform active={call.active} risk={hasClone ? call.latest_risk : "low"} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
