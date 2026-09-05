"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import styles from "./reports.module.css";

interface Report {
  call_id: string;
  timestamp: string;
  duration_seconds: number;
  max_confidence: number;
  risk_level: "low" | "medium" | "high";
  recording_url: string | null;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/reports")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch reports");
        return res.json();
      })
      .then((data) => {
        setReports(data.reports || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError("Unable to load reports. Ensure backend is running.");
        setLoading(false);
      });
  }, []);

  const formatDate = (isoString: string) => {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "medium",
    }).format(d);
  };

  const getRiskColor = (risk: string) => {
    if (risk === "low") return styles.badgeLow;
    if (risk === "medium") return styles.badgeMedium;
    return styles.badgeHigh;
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className={styles.container}>
      <div className={styles.contentWrapper}>
        <header className={styles.header}>
          <div className={styles.titleWrapper}>
            <h1 className={styles.title}>Security Intel</h1>
            <p className={styles.subtitle}>Historical Call Forensics & AI Risk Analysis</p>
          </div>
          <Link href="/" className={styles.backButton}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
            Live Dashboard
          </Link>
        </header>

        {loading && (
          <div style={{ textAlign: "center", padding: "4rem", color: "#888" }}>
            <div style={{ animation: "pulse 2s infinite" }}>Decrypting archives...</div>
          </div>
        )}
        
        {error && <p style={{ textAlign: "center", color: "#ef4444", background: "rgba(239, 68, 68, 0.1)", padding: "1rem", borderRadius: "8px" }}>{error}</p>}

        {!loading && !error && reports.length === 0 && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>🗄️</div>
            <h3>No Records Found</h3>
            <p>The forensic database is currently empty. Run a test call to populate the intel feed.</p>
          </div>
        )}

        <div className={styles.grid}>
          {reports.map((report) => (
            <div key={report.call_id} className={styles.card}>
              <div className={styles.cardHeader}>
                <div>
                  <div className={styles.callId}>{report.call_id}</div>
                  <div className={styles.timestamp}>{formatDate(report.timestamp)}</div>
                </div>
                <div className={`${styles.badge} ${getRiskColor(report.risk_level)}`}>
                  {report.risk_level}
                </div>
              </div>

              <div className={styles.stats}>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Clone Prob.</span>
                  <div className={styles.statValue}>
                    {Math.round(report.max_confidence * 100)}<span>%</span>
                  </div>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Duration</span>
                  <div className={styles.statValue}>
                    {formatDuration(report.duration_seconds)}<span>s</span>
                  </div>
                </div>
              </div>

              <div className={styles.audioContainer}>
                <span className={styles.audioLabel}>Call Recording</span>
                {report.recording_url ? (
                  <audio
                    controls
                    src={`http://localhost:8000${report.recording_url}`}
                    className={styles.audioPlayer}
                  />
                ) : (
                  <p style={{ fontSize: "0.85rem", color: "#666", fontStyle: "italic", margin: 0, padding: "0.5rem 0" }}>
                    Signal lost / No audio captured
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
