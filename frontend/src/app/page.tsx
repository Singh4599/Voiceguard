"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useBackendWS, ChunkEvent } from "@/hooks/useBackendWS";
import ActiveCallsList from "@/components/ActiveCallsList";
import CallAnalysis    from "@/components/CallAnalysis";
import DetectionLog    from "@/components/DetectionLog";
import StatisticsPanel from "@/components/StatisticsPanel";
import {
  VoiceOrb,
  type VoiceOrbState,
} from "@/components/assistant-ui/elements/voice";

interface Toast {
  id: number;
  callId: string;
  msg: string;
}

type ViewState = "orb" | "exploding" | "dashboard";

export default function DashboardPage() {
  const { calls, stats, connected } = useBackendWS();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toasts, setToasts]         = useState<Toast[]>([]);
  const [alertedCalls, setAlertedCalls] = useState<Set<string>>(new Set());
  const [view, setView] = useState<ViewState>("orb");
  const prevCallCount = useRef(0);

  // Auto-select latest active call
  const callList  = Object.values(calls);
  const activeIds = callList.filter((c) => c.active).map((c) => c.call_id);
  const effectiveId = selectedId ?? activeIds[activeIds.length - 1] ?? callList[callList.length - 1]?.call_id ?? null;
  const selectedCall = effectiveId ? calls[effectiveId] ?? null : null;

  // Derive orb state from our connection & call state
  const orbState: VoiceOrbState = !connected ? "connecting" : "speaking";

  // Transition: orb → explode → dashboard when first call arrives
  useEffect(() => {
    const currentCount = callList.length;
    if (view === "orb" && currentCount > 0 && prevCallCount.current === 0) {
      setView("exploding");
      // Render dashboard almost immediately, let clip-path do the slow reveal
      setTimeout(() => setView("dashboard"), 80);
    }
    if (view === "dashboard" && currentCount === 0) {
      setView("orb");
    }
    prevCallCount.current = currentCount;
  }, [callList.length, view]);

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

  // Track alerted calls
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

  return (
    <div className="dashboard">
      {/* ── Topbar ─────────────────────────────────────────── */}
      <header className="topbar">
        {/* Custom logo mark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* SVG icon: shield with waveform */}
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M14 2L4 6.5V14C4 19.5 8.5 24.5 14 26C19.5 24.5 24 19.5 24 14V6.5L14 2Z"
              fill="rgba(5,150,105,0.15)"
              stroke="rgba(16,185,129,0.8)"
              strokeWidth="1.2"
              strokeLinejoin="round"
            />
            <rect x="8"  y="13" width="2" height="4" rx="1" fill="rgba(52,211,153,0.9)" />
            <rect x="11" y="10" width="2" height="7" rx="1" fill="rgba(52,211,153,0.9)" />
            <rect x="14" y="12" width="2" height="5" rx="1" fill="rgba(52,211,153,0.9)" />
            <rect x="17" y="9"  width="2" height="8" rx="1" fill="rgba(52,211,153,0.9)" />
          </svg>

          {/* Wordmark */}
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
            <span style={{
              fontSize: '15px',
              fontWeight: 700,
              letterSpacing: '0.06em',
              color: 'rgba(255,255,255,0.95)',
              fontFamily: 'var(--font-sans)',
              textTransform: 'uppercase',
            }}>
              Voice<span style={{ color: 'rgba(52,211,153,0.95)' }}>Guard</span>
            </span>
            <span style={{
              fontSize: '9px',
              letterSpacing: '0.2em',
              color: 'rgba(255,255,255,0.28)',
              fontFamily: 'var(--font-mono)',
              textTransform: 'uppercase',
              marginTop: '2px',
            }}>
              AI Defense · v2.1
            </span>
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

      {/* ── Orb (idle) or Dashboard (active call) ──────────── */}
      {view === "orb" || view === "exploding" ? (
        <div className="orb-screen">

          {/* ── Ambient radial glow ── */}
          <div style={{
            position: 'absolute', inset: 0, pointerEvents: 'none',
            background: 'radial-gradient(ellipse 520px 420px at 50% calc(50% - 6vh), rgba(5,150,105,0.13) 0%, transparent 70%)',
          }} />

          {/* ── Targeting corner brackets ── */}
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none', marginTop: '-12vh' }}>
            {/* corners: top-left, top-right, bottom-left, bottom-right */}
            {([
              { top: -185, left: -185, rotate: '0deg' },
              { top: -185, right: -185, rotate: '90deg' },
              { bottom: -185, left: -185, rotate: '-90deg' },
              { bottom: -185, right: -185, rotate: '180deg' },
            ] as const).map((pos, idx) => (
              <div key={idx} style={{
                position: 'absolute', width: 32, height: 32,
                borderTop: '2px solid rgba(16,185,129,0.5)',
                borderLeft: '2px solid rgba(16,185,129,0.5)',
                transform: `rotate(${pos.rotate})`,
                ...pos,
              }} />
            ))}

            {/* Dashed orbit arc */}
            <div style={{
              position: 'absolute',
              width: '420px', height: '420px',
              borderRadius: '50%',
              border: '1px dashed rgba(16,185,129,0.18)',
              animation: 'orbit-spin 18s linear infinite',
            }} />

            {/* Floating data labels on orbit */}
            <div style={{ position: 'absolute', top: '-215px', fontSize: '10px', letterSpacing: '0.14em', color: 'rgba(16,185,129,0.55)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>
              VoiceGuard · v2.1
            </div>
            <div style={{ position: 'absolute', right: '-215px', fontSize: '10px', letterSpacing: '0.14em', color: 'rgba(16,185,129,0.55)', fontFamily: 'var(--font-mono)', writingMode: 'vertical-rl' }}>
              {new Date().toLocaleTimeString('en-US', { hour12: false })}
            </div>
          </div>

          {/* ── Orb + label ── */}
          <div className="orb-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '0px', marginTop: '-12vh', position: 'relative', zIndex: 1 }}>
            <VoiceOrb
              state={orbState}
              variant="emerald"
              style={{ width: '340px', height: '340px' }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: connected ? '#10b981' : '#6b7280',
                  boxShadow: connected ? '0 0 8px 3px rgba(16,185,129,0.6)' : 'none',
                  animation: connected ? 'orb-ping 1.5s ease-in-out infinite' : 'none',
                  display: 'inline-block',
                }} />
                <span style={{
                  fontSize: '20px', fontWeight: 600, letterSpacing: '0.04em',
                  color: 'rgba(255,255,255,0.95)', fontFamily: 'var(--font-sans)',
                  textShadow: '0 0 24px rgba(16,185,129,0.4)',
                }}>
                  {!connected ? "Connecting…" : callList.some(c => c.active) ? "Active Call" : "Scanning Network"}
                </span>
              </div>
              <span style={{
                fontSize: '13px', fontWeight: 400, letterSpacing: '0.12em',
                textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)', fontFamily: 'var(--font-sans)',
              }}>
                Waiting for incoming call
              </span>
            </div>
          </div>

          {/* ── Terminal stat cards ── */}
          <div style={{ position: 'absolute', bottom: '80px', display: 'flex', gap: '12px', alignItems: 'stretch' }}>
            {([
              { label: 'CALLS / TODAY', value: String(stats.total).padStart(2,'0'), accent: 'rgba(59,130,246,0.8)' },
              { label: 'AI DETECTED', value: String(stats.ai_detected).padStart(2,'0'), accent: 'rgba(239,68,68,0.7)' },
              { label: 'PROTECTION', value: 'ON', accent: 'rgba(34,197,94,0.8)' },
            ] as const).map(({ label, value, accent }) => (
              <div key={label} style={{
                display: 'flex', flexDirection: 'column', gap: '6px',
                padding: '12px 22px',
                background: 'rgba(0,0,0,0.4)',
                border: '1px solid rgba(255,255,255,0.07)',
                borderLeft: `3px solid ${accent}`,
                borderRadius: '8px',
                minWidth: '110px',
              }}>
                <span style={{ fontSize: '11px', letterSpacing: '0.13em', color: 'rgba(255,255,255,0.3)', fontFamily: 'var(--font-mono)' }}>{label}</span>
                <span style={{ fontSize: '28px', fontWeight: 700, color: 'rgba(255,255,255,0.92)', fontFamily: 'var(--font-mono)', lineHeight: 1 }}>{value}</span>
              </div>
            ))}
          </div>

          <div className="orb-status-bar">
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className={`orb-status-dot ${connected ? 'active' : 'inactive'}`} />
              {connected ? "BACKEND CONNECTED" : "CONNECTING…"}
            </span>
            <span>CALLS TODAY: {stats.total}</span>
            <span>AI DETECTED: {stats.ai_detected}</span>
          </div>
        </div>


      ) : (
        /* Dashboard — slides in via clip-path expanding from orb center */
        <div
          className="panels"
          style={{
            animation: 'orb-portal-reveal 5.5s cubic-bezier(0.25,1,0.5,1) forwards',
          }}
        >
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', height: '100%', overflow: 'hidden' }}>
            <div style={{ flex: '6', minHeight: 0 }}>
              <DetectionLog log={globalLog} stats={stats} />
            </div>
            <div style={{ flex: '4', minHeight: 0 }}>
              <StatisticsPanel stats={stats} />
            </div>
          </div>
        </div>
      )}

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
