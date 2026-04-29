import React, {
  useState, useRef, useEffect, useCallback,
  forwardRef, useImperativeHandle,
} from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Sentiment = 'bullish' | 'bearish' | 'neutral';
type CardStatus = 'idle' | 'running' | 'complete' | 'error';

interface SectionData {
  agent: string;
  title: string;
  sentiment: Sentiment;
  confidence: number;
  content: string;
  key_points: string[];
  duration_seconds: number;
  error?: string;
}

export interface AgentMeta {
  title: string;
  role: string;
  tools: string[];
  icon?: string;
}

export interface AgentCardHandle {
  triggerRun: (ticker: string, title: string, description: string) => void;
}

interface AgentCardProps {
  agentKey: string;
  meta: AgentMeta;
  onAssign: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = `http://${window.location.hostname}:8000`;
const WS_BASE  = `ws://${window.location.hostname}:8000`;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SentimentChip({ sentiment, confidence }: { sentiment: Sentiment; confidence?: number }) {
  const cfg = {
    bullish: { bg: 'rgba(16,185,129,0.09)', color: '#059669', border: 'rgba(16,185,129,0.28)', dot: '#10B981', label: 'Bullish' },
    bearish: { bg: 'rgba(239,68,68,0.09)',  color: '#DC2626', border: 'rgba(239,68,68,0.28)',  dot: '#EF4444', label: 'Bearish' },
    neutral: { bg: 'rgba(245,158,11,0.09)', color: '#D97706', border: 'rgba(245,158,11,0.28)', dot: '#F59E0B', label: 'Neutral' },
  }[sentiment];

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 9px', borderRadius: 100,
      background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color,
      fontSize: 11, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace',
      letterSpacing: '0.01em', whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: cfg.dot, flexShrink: 0 }} />
      {cfg.label}{confidence !== undefined ? ` · ${Math.round(confidence * 100)}%` : ''}
    </span>
  );
}

function ToolPill({ label }: { label: string }) {
  return (
    <span style={{
      fontSize: 10, padding: '2px 7px', borderRadius: 100,
      background: '#F5F5F5', color: '#9CA3AF',
      fontFamily: 'IBM Plex Mono, monospace', border: '1px solid #EEEEEE',
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

function formatDuration(s: number) {
  if (s < 60) return `${Math.round(s)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

// ---------------------------------------------------------------------------
// AgentCard
// ---------------------------------------------------------------------------

const AgentCard = forwardRef<AgentCardHandle, AgentCardProps>(
  ({ agentKey, meta, onAssign }, ref) => {
    const [status, setStatus]           = useState<CardStatus>('idle');
    const [activeTicker, setActiveTicker] = useState('');
    const [currentStep, setCurrentStep] = useState('');
    const [section, setSection]         = useState<SectionData | null>(null);
    const [expanded, setExpanded]       = useState(false);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => () => { wsRef.current?.close(); }, []);

    // Core run logic — called by the imperative handle
    const doRun = useCallback(async (ticker: string, focus: string) => {
      try {
        const res = await fetch(`${API_BASE}/research/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ticker,
            agents: [agentKey],
            focus: focus.trim() || undefined,
          }),
        });
        const data = await res.json() as { run_id: string };

        const ws = new WebSocket(`${WS_BASE}/ws/research/${data.run_id}`);
        wsRef.current = ws;

        ws.onmessage = (ev) => {
          let event: Record<string, unknown>;
          try { event = JSON.parse(ev.data as string); } catch { return; }

          if (event.type === 'fetch_complete')
            setCurrentStep('Market data loaded. Starting analysis...');
          if (event.type === 'agent_step')
            setCurrentStep(String(event.step ?? ''));

          if (event.type === 'agent_complete') {
            const s = event.section as SectionData;
            setSection(s);
            setStatus(s.error ? 'error' : 'complete');
            setCurrentStep('');
            ws.close();
          }
        };

        ws.onerror = () => {
          setCurrentStep('');
          setStatus('error');
          setSection({
            agent: agentKey, title: meta.title,
            sentiment: 'neutral', confidence: 0,
            content: '', key_points: [], duration_seconds: 0,
            error: 'WebSocket connection failed — check backend.',
          });
        };
      } catch {
        setStatus('error');
        setSection({
          agent: agentKey, title: meta.title,
          sentiment: 'neutral', confidence: 0,
          content: '', key_points: [], duration_seconds: 0,
          error: 'Could not reach backend.',
        });
      }
    }, [agentKey, meta.title]);

    // Expose triggerRun to parent via ref
    useImperativeHandle(ref, () => ({
      triggerRun: (ticker: string, _title: string, description: string) => {
        wsRef.current?.close();
        setActiveTicker(ticker.toUpperCase());
        setSection(null);
        setExpanded(false);
        setCurrentStep('Initialising...');
        setStatus('running');
        doRun(ticker.toUpperCase(), description);
      },
    }), [doRun]);

    const resetCard = useCallback((e: React.MouseEvent) => {
      e.stopPropagation();
      wsRef.current?.close();
      setStatus('idle');
      setActiveTicker('');
      setSection(null);
      setCurrentStep('');
      setExpanded(false);
    }, []);

    // ── Visual tokens ─────────────────────────────────────────────────────
    const tokens = (() => {
      if (status === 'running')
        return { border: 'rgba(16,185,129,0.35)', bg: 'rgba(16,185,129,0.03)' };
      if (status === 'complete' && section) {
        if (section.sentiment === 'bullish') return { border: 'rgba(16,185,129,0.3)',  bg: 'rgba(16,185,129,0.03)' };
        if (section.sentiment === 'bearish') return { border: 'rgba(239,68,68,0.3)',   bg: 'rgba(239,68,68,0.025)' };
        return { border: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.025)' };
      }
      if (status === 'error') return { border: 'rgba(239,68,68,0.3)', bg: 'rgba(239,68,68,0.025)' };
      return { border: '#EEEEEE', bg: '#FFFFFF' };
    })();

    const clickable = status === 'idle' || status === 'complete' || status === 'error';

    // ── Render ────────────────────────────────────────────────────────────
    return (
      <div
        onClick={clickable ? onAssign : undefined}
        style={{
          background: tokens.bg,
          border: `1px solid ${tokens.border}`,
          borderRadius: 10,
          padding: '16px 18px',
          cursor: clickable ? 'pointer' : 'default',
          transition: 'border-color 0.15s ease, background 0.15s ease',
          position: 'relative',
        }}
      >
        {/* ── IDLE ───────────────────────────────────────────────────────── */}
        {status === 'idle' && (
          <>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A', fontFamily: 'IBM Plex Sans, sans-serif', letterSpacing: '-0.01em' }}>
                {meta.title}
              </span>
              <span style={{
                width: 20, height: 20, borderRadius: '50%', background: '#F5F5F5',
                border: '1px solid #EEEEEE', display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 14, color: '#BEBEBE',
                flexShrink: 0, marginLeft: 8, lineHeight: 1,
              }}>+</span>
            </div>
            <p style={{ fontSize: 11, color: '#9CA3AF', fontStyle: 'italic', margin: '0 0 10px', fontFamily: 'IBM Plex Sans, sans-serif', lineHeight: 1.45 }}>
              {meta.role}
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {meta.tools.map(t => <ToolPill key={t} label={t} />)}
            </div>
            <p style={{ fontSize: 10, color: '#D1D5DB', margin: '12px 0 0', fontFamily: 'IBM Plex Mono, monospace' }}>
              Click to assign
            </p>
          </>
        )}

        {/* ── RUNNING ────────────────────────────────────────────────────── */}
        {status === 'running' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  width: 7, height: 7, borderRadius: '50%', background: '#10B981', flexShrink: 0,
                  animation: 'agentPulse 1.4s ease-in-out infinite',
                }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A', fontFamily: 'IBM Plex Sans, sans-serif', letterSpacing: '-0.01em' }}>
                  {meta.title}
                </span>
              </div>
              <span style={{ fontSize: 9, fontWeight: 700, color: '#10B981', fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '0.08em' }}>
                LIVE
              </span>
            </div>
            <p style={{ fontSize: 12, fontWeight: 600, color: '#10B981', margin: '0 0 6px', fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '0.01em' }}>
              {activeTicker}
            </p>
            <p style={{ fontSize: 11, color: '#6B7280', margin: 0, fontFamily: 'IBM Plex Sans, sans-serif', lineHeight: 1.5, fontStyle: 'italic', minHeight: 16 }}>
              {currentStep || 'Working...'}
            </p>
          </>
        )}

        {/* ── COMPLETE ───────────────────────────────────────────────────── */}
        {status === 'complete' && section && (
          <>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
                  <span style={{
                    width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
                    background: section.sentiment === 'bullish' ? '#10B981' : section.sentiment === 'bearish' ? '#EF4444' : '#F59E0B',
                    color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 8, fontWeight: 700,
                  }}>✓</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A', fontFamily: 'IBM Plex Sans, sans-serif', letterSpacing: '-0.01em' }}>
                    {meta.title}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#10B981', fontFamily: 'IBM Plex Mono, monospace' }}>
                    {activeTicker}
                  </span>
                  {section.duration_seconds > 0 && (
                    <span style={{ fontSize: 10, color: '#BEBEBE', fontFamily: 'IBM Plex Mono, monospace' }}>
                      {formatDuration(section.duration_seconds)}
                    </span>
                  )}
                </div>
              </div>
              <button onClick={resetCard} title="Reassign" style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#BEBEBE', fontSize: 12, padding: '2px 4px',
                fontFamily: 'IBM Plex Mono, monospace', flexShrink: 0,
              }}>↺</button>
            </div>

            <div style={{ marginBottom: 10 }}>
              <SentimentChip sentiment={section.sentiment} confidence={section.confidence} />
            </div>

            {section.key_points.length > 0 && (
              <div style={{ borderTop: '1px solid #F3F3F3', paddingTop: 10 }}>
                {(expanded ? section.key_points : section.key_points.slice(0, 3)).map((pt, i) => (
                  <p key={i} style={{
                    fontSize: 11, color: '#4B5563', margin: '0 0 4px',
                    fontFamily: 'IBM Plex Sans, sans-serif', lineHeight: 1.45,
                    paddingLeft: 10, position: 'relative',
                  }}>
                    <span style={{ position: 'absolute', left: 0, color: '#10B981', fontWeight: 700 }}>·</span>
                    {pt}
                  </p>
                ))}
                {section.key_points.length > 3 && (
                  <button
                    onClick={e => { e.stopPropagation(); setExpanded(!expanded); }}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0 0',
                      fontSize: 10, color: '#9CA3AF', fontFamily: 'IBM Plex Mono, monospace',
                      textDecoration: 'underline',
                    }}
                  >
                    {expanded ? 'Show less' : `+${section.key_points.length - 3} more`}
                  </button>
                )}
              </div>
            )}
          </>
        )}

        {/* ── ERROR ──────────────────────────────────────────────────────── */}
        {status === 'error' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span style={{
                  width: 14, height: 14, borderRadius: '50%', background: '#EF4444',
                  color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 8, fontWeight: 700, flexShrink: 0,
                }}>✕</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A', fontFamily: 'IBM Plex Sans, sans-serif', letterSpacing: '-0.01em' }}>
                  {meta.title}
                </span>
              </div>
              <button onClick={resetCard} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#BEBEBE', fontSize: 12, padding: '2px 4px',
                fontFamily: 'IBM Plex Mono, monospace',
              }}>↺</button>
            </div>
            <p style={{ fontSize: 11, color: '#DC2626', margin: '0 0 10px', fontFamily: 'IBM Plex Sans, sans-serif', lineHeight: 1.45 }}>
              {section?.error?.slice(0, 140) ?? 'An error occurred.'}
            </p>
            <button
              onClick={e => { e.stopPropagation(); onAssign(); }}
              style={{
                background: 'none', border: '1px solid #EEEEEE', borderRadius: 6,
                cursor: 'pointer', padding: '4px 10px',
                fontSize: 11, color: '#6B7280', fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            >Try again</button>
          </>
        )}

        <style>{`
          @keyframes agentPulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50%       { opacity: 0.45; transform: scale(0.8); }
          }
        `}</style>
      </div>
    );
  }
);

AgentCard.displayName = 'AgentCard';
export default AgentCard;
