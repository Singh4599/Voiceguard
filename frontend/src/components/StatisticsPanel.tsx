import React from 'react';

interface StatsProps {
  stats: {
    total: number;
    ai_detected: number;
    false_alerts?: number;
    avg_response?: string;
  };
}

export default function StatisticsPanel({ stats }: StatsProps) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', padding: '16px 20px' }}>
      <h3 style={{ 
        fontFamily: 'var(--font-sans)', 
        fontSize: '13px', 
        fontWeight: 600,
        textTransform: 'uppercase', 
        letterSpacing: '0.1em', 
        color: 'var(--text-1)',
        margin: 0
      }}>
        Statistics Today
      </h3>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '4px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-2)' }}>Total Calls</span>
          <span style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-sans)', color: 'var(--text-1)', lineHeight: 1 }}>
            {stats.total}
          </span>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-2)' }}>AI Detected</span>
          <span style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-sans)', color: 'var(--text-1)', lineHeight: 1 }}>
            {stats.ai_detected}
          </span>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-2)' }}>False Alerts</span>
          <span style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-sans)', color: 'var(--text-1)', lineHeight: 1 }}>
            {stats.false_alerts || 0}
          </span>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-2)' }}>Avg Response</span>
          <span style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-sans)', color: 'var(--text-1)', lineHeight: 1 }}>
            {stats.avg_response || '1.8s'}
          </span>
        </div>
      </div>
    </div>
  );
}
