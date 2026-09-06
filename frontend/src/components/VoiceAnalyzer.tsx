"use client";
import { useState, useRef, useCallback } from "react";

interface AnalysisResult {
  is_clone: boolean;
  confidence: number;
  risk_level: string;
  label: string;
  indicators: string[];
  raw_scores: Record<string, number>;
  error?: string;
}

export default function VoiceAnalyzer() {
  const [dragging, setDragging]   = useState(false);
  const [file, setFile]           = useState<File | null>(null);
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState<AnalysisResult | null>(null);
  const [error, setError]         = useState<string | null>(null);
  const inputRef                  = useRef<HTMLInputElement>(null);

  const analyze = useCallback(async (f: File) => {
    setFile(f);
    setResult(null);
    setError(null);
    setLoading(true);

    try {
      const form = new FormData();
      form.append("file", f);

      const res = await fetch("http://localhost:8000/api/analyze", {
        method: "POST",
        body: form,
      });

      const data: AnalysisResult = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) analyze(f);
    },
    [analyze]
  );

  const riskColor = (risk: string) => {
    switch (risk) {
      case "critical": return "#ef4444";
      case "high":     return "#f97316";
      case "medium":   return "#eab308";
      default:         return "#10b981";
    }
  };

  const resultBg = result
    ? result.is_clone
      ? "rgba(239,68,68,0.08)"
      : "rgba(16,185,129,0.08)"
    : "transparent";

  const resultBorder = result
    ? result.is_clone
      ? "rgba(239,68,68,0.35)"
      : "rgba(16,185,129,0.35)"
    : "transparent";

  return (
    <div style={{
      background: "rgba(0,0,0,0.35)",
      border: "1px solid rgba(16,185,129,0.15)",
      borderRadius: "16px",
      padding: "24px",
      display: "flex",
      flexDirection: "column",
      gap: "16px",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <span style={{ color: "#e2e8f0", fontWeight: 600, fontSize: "14px", letterSpacing: "0.05em" }}>
          VOICE ANALYZER
        </span>
        <span style={{
          marginLeft: "auto", fontSize: "11px", color: "#64748b",
          background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.2)",
          padding: "2px 8px", borderRadius: "20px"
        }}>
          WAV · MP3 · OGG
        </span>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? "#10b981" : "rgba(16,185,129,0.25)"}`,
          borderRadius: "12px",
          padding: "28px 20px",
          textAlign: "center",
          cursor: "pointer",
          background: dragging ? "rgba(16,185,129,0.06)" : "rgba(16,185,129,0.02)",
          transition: "all 0.2s ease",
          position: "relative",
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".wav,.mp3,.ogg,.m4a,.flac"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) analyze(f); }}
        />

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
            <div style={{
              width: "36px", height: "36px", border: "3px solid rgba(16,185,129,0.2)",
              borderTopColor: "#10b981", borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }} />
            <span style={{ color: "#94a3b8", fontSize: "13px" }}>Analyzing voice...</span>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: "8px" }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
                stroke={dragging ? "#10b981" : "#475569"} strokeWidth="1.5"
                style={{ margin: "0 auto" }}>
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="22"/>
                <line x1="8" y1="22" x2="16" y2="22"/>
              </svg>
            </div>
            <p style={{ color: file ? "#10b981" : "#64748b", fontSize: "13px", margin: 0 }}>
              {file ? `📄 ${file.name}` : "Drop audio file here or click to browse"}
            </p>
            <p style={{ color: "#334155", fontSize: "11px", margin: "4px 0 0" }}>
              Supports WAV, MP3, OGG, M4A, FLAC
            </p>
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
          borderRadius: "10px", padding: "12px 16px", color: "#f87171", fontSize: "13px"
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Result */}
      {result && !error && (
        <div style={{
          background: resultBg, border: `1px solid ${resultBorder}`,
          borderRadius: "12px", padding: "20px",
          animation: "fadeIn 0.4s ease",
        }}>
          {/* Main verdict */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
            <div style={{
              width: "48px", height: "48px", borderRadius: "50%",
              background: result.is_clone ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.15)",
              border: `2px solid ${result.is_clone ? "#ef4444" : "#10b981"}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: "22px",
            }}>
              {result.is_clone ? "🤖" : "✅"}
            </div>
            <div>
              <div style={{
                fontSize: "16px", fontWeight: 700,
                color: result.is_clone ? "#f87171" : "#34d399",
              }}>
                {result.label}
              </div>
              <div style={{ fontSize: "12px", color: "#64748b", marginTop: "2px" }}>
                {result.confidence}% confidence · Risk:{" "}
                <span style={{ color: riskColor(result.risk_level), fontWeight: 600 }}>
                  {result.risk_level.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Confidence bar */}
            <div style={{ marginLeft: "auto", textAlign: "right" }}>
              <div style={{
                width: "80px", height: "6px", background: "rgba(255,255,255,0.08)",
                borderRadius: "3px", overflow: "hidden",
              }}>
                <div style={{
                  height: "100%", borderRadius: "3px",
                  width: `${result.confidence}%`,
                  background: result.is_clone
                    ? "linear-gradient(90deg,#ef4444,#f97316)"
                    : "linear-gradient(90deg,#10b981,#34d399)",
                  transition: "width 0.8s ease",
                }} />
              </div>
              <div style={{ color: "#475569", fontSize: "11px", marginTop: "4px" }}>
                {result.confidence}%
              </div>
            </div>
          </div>

          {/* Indicators */}
          {result.indicators?.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <div style={{ fontSize: "11px", color: "#475569", letterSpacing: "0.08em", marginBottom: "4px" }}>
                DETECTION SIGNALS
              </div>
              {result.indicators.map((ind, i) => (
                <div key={i} style={{
                  fontSize: "12px", color: "#94a3b8",
                  padding: "6px 10px",
                  background: "rgba(255,255,255,0.03)",
                  borderRadius: "6px",
                  borderLeft: `3px solid ${result.is_clone ? "#ef4444" : "#10b981"}`,
                }}>
                  {ind}
                </div>
              ))}
            </div>
          )}

          {/* Analyze another */}
          <button
            onClick={() => { setResult(null); setFile(null); setError(null); inputRef.current?.click(); }}
            style={{
              marginTop: "14px", width: "100%", padding: "8px",
              background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)",
              borderRadius: "8px", color: "#10b981", fontSize: "13px", cursor: "pointer",
              transition: "all 0.2s",
            }}
            onMouseOver={(e) => (e.currentTarget.style.background = "rgba(16,185,129,0.15)")}
            onMouseOut={(e) => (e.currentTarget.style.background = "rgba(16,185,129,0.08)")}
          >
            Analyze Another File
          </button>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
      `}</style>
    </div>
  );
}
