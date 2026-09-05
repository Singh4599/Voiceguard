"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useBackendWS, ChunkEvent } from "@/hooks/useBackendWS";
import ActiveCallsList from "@/components/ActiveCallsList";
import CallAnalysis    from "@/components/CallAnalysis";
import DetectionLog    from "@/components/DetectionLog";

interface Toast {
  id: number;
  callId: string;
  msg: string;
}

export default function DashboardPage() {
  const { calls, stats, connected } = useBackendWS();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toasts, setToasts]         = useState<Toast[]>([]);
  const [alertedCalls, setAlertedCalls] = useState<Set<string>>(new Set());

  // Auto-select latest active call
  const callList  = Object.values(calls);
  const activeIds = callList.filter((c) => c.active).map((c) => c.call_id);
  const effectiveId = selectedId ?? activeIds[activeIds.length - 1] ?? callList[callList.length - 1]?.call_id ?? null;
  const selectedCall = effectiveId ? calls[effectiveId] ?? null : null;

  // Watch for AI detections → show toast
  const lastChunks = callList.flatMap((c) => c.chunks.slice(-1));
  useEffect(() => {
    lastChunks.forEach((ev: ChunkEvent) => {
      if (ev.confidence > 0.45) {
        setToasts((prev) => {
          if (prev.some((t) => t.callId === ev.call_id)) return prev;
          const t: Toast = {
            id: Date.now(),
            callId: ev.call_id,
            msg: `AI Clone detected — ${Math.round(ev.confidence * 100)}% confidence`,
          };
          setTimeout(() => setToasts((p) => p.filter((x) => x.id !== t.id)), 5000);
          return [...prev, t];
        });
      }
    });
  }, [JSON.stringify(lastChunks.map((e) => e?.chunk))]);

  // Track alerted calls from backend alert_sent events
  const handleAlertSent = useCallback((callId: string) => {
    setAlertedCalls((prev) => new Set(prev).add(callId));
  }, []);

  // Build log
  const globalLog: ChunkEvent[] = selectedCall
    ? selectedCall.chunks
    : callList
        .flatMap((c) => c.chunks)
        .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        .slice(-100);

  // Topbar stats
  const liveCount = callList.filter((c) => c.active).length;
  const todayAI   = stats.ai_detected;

  return (
    <div className="dashboard">
      {/* ── Topbar ─────────────────────────────────────────── */}
      <header className="topbar">
        <span className="topbar-wordmark">VoiceGuard</span>

        <div className="topbar-center">
          <div className="topbar-stat">
            <span className="topbar-stat-label">Live Calls</span>
            <span className={`topbar-stat-value ${liveCount > 0 ? "teal" : ""}`}>
              {liveCount}
            </span>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-label">AI Detected</span>
            <span className={`topbar-stat-value ${todayAI > 0 ? "danger" : ""}`}>
              {todayAI}
            </span>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-label">Total Calls</span>
            <span className="topbar-stat-value">{stats.total}</span>
          </div>
        </div>

        <div className="topbar-right" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Link href="/reports" style={{ 
            color: 'white', 
            textDecoration: 'none', 
            fontSize: '0.85rem', 
            fontWeight: 600, 
            background: 'rgba(255,255,255,0.1)', 
            padding: '0.4rem 0.8rem', 
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.2)',
            transition: 'all 0.2s'
          }}>
            📋 View Reports
          </Link>
          <span className="font-mono" style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.08em" }}>
            SIH 2026 · #26104
          </span>
          <div className={`status-pill ${connected ? "connected" : "disconnected"}`}>
            <span className="dot" />
            {connected ? "SYSTEM ACTIVE" : "RECONNECTING"}
          </div>
        </div>
      </header>

      {/* ── Panels ─────────────────────────────────────────── */}
      <div className="panels">
        <ActiveCallsList
          calls={calls}
          selectedId={effectiveId}
          alertedCalls={alertedCalls}
          onSelect={setSelectedId}
        />
        <CallAnalysis
          call={selectedCall}
          isAlerted={effectiveId ? alertedCalls.has(effectiveId) : false}
        />
        <DetectionLog log={globalLog} stats={stats} />
      </div>

      {/* ── Toast Notifications ─────────────────────────────── */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            <span className="toast-icon">🚨</span>
            <div className="toast-body">
              <div className="toast-title">AI CLONE DETECTED</div>
              <div className="toast-msg">{t.msg}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
