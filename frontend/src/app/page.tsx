"use client";
import { useState } from "react";
import { useBackendWS, ChunkEvent } from "@/hooks/useBackendWS";
import ActiveCallsList from "@/components/ActiveCallsList";
import CallAnalysis    from "@/components/CallAnalysis";
import DetectionLog    from "@/components/DetectionLog";

export default function DashboardPage() {
  const { calls, stats, connected } = useBackendWS();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Auto-select latest active call if nothing selected
  const callList = Object.values(calls);
  const activeIds = callList.filter((c) => c.active).map((c) => c.call_id);
  const effectiveId = selectedId ?? activeIds[activeIds.length - 1] ?? callList[callList.length - 1]?.call_id ?? null;
  const selectedCall = effectiveId ? calls[effectiveId] ?? null : null;

  // Build global log from selected call or all calls
  const globalLog: ChunkEvent[] = selectedCall
    ? selectedCall.chunks
    : callList.flatMap((c) => c.chunks).sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      ).slice(-100);

  return (
    <div className="dashboard">
      {/* ── Topbar ───────────────────────────────────────────── */}
      <header className="topbar">
        <span className="topbar-wordmark">VoiceGuard</span>
        <div className="topbar-right">
          <span
            className="font-mono"
            style={{ fontSize: 10, color: "var(--text-3)" }}
          >
            SIH 2026 · Problem 26104
          </span>
          <div className="status-pill">
            <span className="dot" style={{ background: connected ? "var(--teal)" : "var(--danger)" }} />
            {connected ? "SYSTEM ACTIVE" : "RECONNECTING"}
          </div>
        </div>
      </header>

      {/* ── 3-Column Panels ──────────────────────────────────── */}
      <div className="panels">
        <ActiveCallsList
          calls={calls}
          selectedId={effectiveId}
          onSelect={setSelectedId}
        />
        <CallAnalysis call={selectedCall} />
        <DetectionLog log={globalLog} stats={stats} />
      </div>
    </div>
  );
}
