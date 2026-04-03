import { useState, useRef, KeyboardEvent, useCallback } from 'react';
import { streamMemo, MemoEvent } from '../api';

// ─── Types ────────────────────────────────────────────────────────────────────

type PageState = 'idle' | 'analyzing' | 'memo_ready';

interface AgentCard {
  name: string;
  view?: string;
  confidence?: number;
  reasoning?: string;
  done: boolean;
}

interface StructuredMemo {
  thesis: string | null;
  bear_case: string | null;
  key_risks: string[] | null;
  valuation_range: { bear: string; base: string; bull: string } | null;
  what_would_make_this_wrong: string | null;
}

interface MemoResult {
  verdict: 'BUY' | 'WATCH' | 'PASS';
  confidence: number;
  structured_memo: StructuredMemo;
  agent_signals: Record<string, { view: string; confidence: number; reasoning: string }>;
  debate_log: Array<{ round: number; agent: string; action: string; content: string }>;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const AGENT_META: Record<string, { label: string; role: string; color: string }> = {
  fundamental: { label: 'Fundamental', role: 'Valuation & Earnings Quality',  color: '#3B82F6' },
  risk:        { label: 'Risk',        role: 'Leverage & Liquidity',    color: '#EF4444' },
  quant:       { label: 'Quant',       role: 'Momentum & Factors',      color: '#8B5CF6' },
  macro:       { label: 'Macro',       role: 'Rates & Cycle',           color: '#F59E0B' },
  sentiment:   { label: 'Sentiment',   role: 'News & Analyst Flow',     color: '#10B981' },
};

const INITIAL_AGENTS: AgentCard[] = Object.keys(AGENT_META).map(name => ({
  name,
  done: false,
}));

const VERDICT_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  BUY:   { bg: '#F0FDF4', text: '#15803D', border: '#16A34A' },
  WATCH: { bg: '#FFFBEB', text: '#92400E', border: '#D97706' },
  PASS:  { bg: '#FFF1F2', text: '#9F1239', border: '#E11D48' },
};

const VIEW_COLORS: Record<string, string> = {
  bullish:  '#16A34A',
  bearish:  '#DC2626',
  cautious: '#D97706',
  neutral:  '#6B7280',
};

const CHECKLIST_ITEMS = [
  'Why now? What\'s the catalyst for acting on this analysis today?',
  'What specific event would make you exit this position?',
  'Max position size (% of portfolio)?',
  'What metric will you check next quarter to confirm or challenge this thesis?',
];

// ─── Sub-components ────────────────────────────────────────────────────────────

function AgentCardRow({ card }: { card: AgentCard }) {
  const meta = AGENT_META[card.name] || { label: card.name, role: '', color: '#6B7280' };
  const viewColor = card.view ? VIEW_COLORS[card.view] || '#6B7280' : '#6B7280';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        padding: '12px 16px',
        borderBottom: '1px solid #E5E7EB',
        opacity: card.done ? 1 : 0.5,
        transition: 'opacity 0.3s ease',
      }}
    >
      {/* Initials badge */}
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 6,
          background: `${meta.color}18`,
          border: `1.5px solid ${meta.color}40`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          fontFamily: 'IBM Plex Mono, monospace',
          fontSize: 11,
          fontWeight: 700,
          color: meta.color,
          letterSpacing: '0.02em',
        }}
      >
        {card.name.slice(0, 2).toUpperCase()}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
          <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 12, fontWeight: 600, color: '#1A1A1A' }}>
            {meta.label}
          </span>
          <span style={{ fontSize: 11, color: '#9CA3AF' }}>{meta.role}</span>
          {card.done && card.view && (
            <span
              style={{
                marginLeft: 'auto',
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: 10,
                fontWeight: 700,
                color: viewColor,
                background: `${viewColor}14`,
                padding: '2px 8px',
                borderRadius: 4,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {card.view} {card.confidence !== undefined ? `${(card.confidence * 100).toFixed(0)}%` : ''}
            </span>
          )}
          {!card.done && (
            <span
              style={{
                marginLeft: 'auto',
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: 10,
                color: '#9CA3AF',
                letterSpacing: '0.04em',
              }}
            >
              analyzing...
            </span>
          )}
        </div>
        {card.done && card.reasoning && (
          <p style={{ fontSize: 12, color: '#374151', lineHeight: 1.5, margin: 0, fontFamily: 'Inter, sans-serif' }}>
            {card.reasoning}
          </p>
        )}
      </div>
    </div>
  );
}


function VerdictBanner({
  verdict,
  confidence,
  ticker,
  onToggleReasoning,
  showReasoning,
}: {
  verdict: 'BUY' | 'WATCH' | 'PASS';
  confidence: number;
  ticker: string;
  onToggleReasoning: () => void;
  showReasoning: boolean;
}) {
  const styles = VERDICT_STYLES[verdict] || VERDICT_STYLES.WATCH;
  const pct = Math.round(confidence * 100);

  return (
    <div
      style={{
        background: styles.bg,
        border: `1.5px solid ${styles.border}`,
        borderRadius: 8,
        padding: '16px 20px',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        flexWrap: 'wrap',
      }}
    >
      <div
        style={{
          fontFamily: 'IBM Plex Mono, monospace',
          fontSize: 28,
          fontWeight: 700,
          color: styles.text,
          letterSpacing: '-0.02em',
          lineHeight: 1,
        }}
      >
        {verdict}
      </div>
      <div style={{ flex: 1, minWidth: 140 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: styles.text, fontFamily: 'IBM Plex Mono, monospace' }}>
            {ticker} — Committee Consensus
          </span>
          <span style={{ fontSize: 12, fontWeight: 700, color: styles.text, fontFamily: 'IBM Plex Mono, monospace' }}>
            {pct}%
          </span>
        </div>
        <div style={{ height: 6, background: `${styles.border}30`, borderRadius: 3, overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${pct}%`,
              background: styles.border,
              borderRadius: 3,
              transition: 'width 0.8s ease',
            }}
          />
        </div>
      </div>
      <button
        onClick={onToggleReasoning}
        style={{
          fontSize: 12,
          color: styles.text,
          background: 'none',
          border: `1px solid ${styles.border}60`,
          borderRadius: 6,
          padding: '4px 10px',
          cursor: 'pointer',
          fontFamily: 'IBM Plex Mono, monospace',
          letterSpacing: '0.02em',
        }}
      >
        {showReasoning ? 'Hide reasoning' : 'Show reasoning'}
      </button>
    </div>
  );
}


function MemoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        border: '1px solid #E5E7EB',
        borderRadius: 8,
        overflow: 'hidden',
        background: '#FFFFFF',
      }}
    >
      <div
        style={{
          padding: '8px 16px',
          borderBottom: '1px solid #E5E7EB',
          background: '#F9FAFB',
        }}
      >
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: 10,
            fontWeight: 700,
            color: '#6B7280',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          {title}
        </span>
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}


function Unavailable() {
  return (
    <p style={{ fontSize: 13, color: '#9CA3AF', fontStyle: 'italic', margin: 0 }}>
      Analysis unavailable
    </p>
  );
}


// ─── Main Page ────────────────────────────────────────────────────────────────

export default function InvestmentMemoPage() {
  const [pageState, setPageState] = useState<PageState>('idle');
  const [ticker, setTicker] = useState('');
  const [queryMode, setQueryMode] = useState('full_ic');
  const [agents, setAgents] = useState<AgentCard[]>(INITIAL_AGENTS);
  const [statusLine, setStatusLine] = useState('');
  const [result, setResult] = useState<MemoResult | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);
  const [checklist, setChecklist] = useState<Record<number, string>>({});
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeTicker = useRef('');
  const cancelRef = useRef<(() => void) | null>(null);

  const handleEvent = (event: MemoEvent) => {
    switch (event.type) {
      case 'arena_dispatch':
        setStatusLine('Dispatching agents...');
        break;

      case 'arena_signal':
      case 'arena_agent_done': {
        const agentName: string = event.agent || '';
        setAgents(prev =>
          prev.map(card =>
            card.name === agentName
              ? {
                  ...card,
                  done: true,
                  view: event.view,
                  confidence: event.confidence,
                  reasoning: event.reasoning || event.signal?.reasoning || '',
                }
              : card
          )
        );
        break;
      }

      case 'arena_conflict':
        setStatusLine(`Conflict detected — continuing debate...`);
        break;

      case 'arena_synthesis':
        setStatusLine('Synthesizing investment memo...');
        break;

      case 'arena_memo_ready':
        setResult({
          verdict: event.verdict,
          confidence: event.confidence,
          structured_memo: event.structured_memo,
          agent_signals: event.agent_signals || {},
          debate_log: event.debate_log || [],
        });
        setPageState('memo_ready');
        setStatusLine('');
        break;

      case 'error':
        setError(event.error || 'Unknown error');
        setPageState('idle');
        break;
    }
  };

  const handleSubmit = () => {
    const t = ticker.trim().toUpperCase();
    if (!t || pageState === 'analyzing') return;
    activeTicker.current = t;
    setError(null);
    setResult(null);
    setShowReasoning(false);
    setChecklist({});
    setAgents(INITIAL_AGENTS);
    setStatusLine('Initializing debate...');
    setPageState('analyzing');

    const { cancel } = streamMemo(t, queryMode, handleEvent, (err) => {
      if (err !== null) setError(err);
      setPageState('idle');
    });
    cancelRef.current = cancel;
  };

  const handleCancel = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
    setResult(null);
    setAgents(INITIAL_AGENTS);
    setStatusLine('');
    setPageState('idle');
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const handleSave = () => {
    if (!result) return;
    const memo = result.structured_memo;
    const text = [
      `INVESTMENT MEMO — ${activeTicker.current}`,
      `Verdict: ${result.verdict} (${Math.round(result.confidence * 100)}% consensus)`,
      '',
      'THESIS',
      memo.thesis || 'N/A',
      '',
      'BEAR CASE',
      memo.bear_case || 'N/A',
      '',
      'KEY RISKS',
      ...(memo.key_risks || ['N/A']).map((r, i) => `${i + 1}. ${r}`),
      '',
      'VALUATION RANGE',
      memo.valuation_range
        ? `Bear: ${memo.valuation_range.bear}  Base: ${memo.valuation_range.base}  Bull: ${memo.valuation_range.bull}`
        : 'N/A',
      '',
      'WHAT WOULD MAKE THIS WRONG',
      memo.what_would_make_this_wrong || 'N/A',
      '',
      'DECISION CHECKLIST',
      ...CHECKLIST_ITEMS.map((q, i) => `${q}\n→ ${checklist[i] || '(not answered)'}`),
    ].join('\n');

    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => setError('Could not copy to clipboard — select the text manually'));
  };

  const allChecked = CHECKLIST_ITEMS.every((_, i) => (checklist[i] || '').trim().length > 0);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      style={{
        marginLeft: 80,
        minHeight: '100vh',
        background: '#FFFFFF',
        fontFamily: 'Inter, -apple-system, sans-serif',
        color: '#1A1A1A',
      }}
    >
      <div style={{ maxWidth: 860, margin: '0 auto', padding: '48px 24px 80px' }}>

        {/* Header */}
        <div style={{ marginBottom: 32 }}>
          <h1
            style={{
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: 22,
              fontWeight: 700,
              color: '#1A1A1A',
              margin: '0 0 6px',
              letterSpacing: '-0.02em',
            }}
          >
            Investment Memo
          </h1>
          <p style={{ fontSize: 14, color: '#6B7280', margin: 0 }}>
            Enter a ticker. Get a 5-analyst investment committee memo in 90 seconds.
          </p>
        </div>

        {/* Input bar */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            marginBottom: 32,
            alignItems: 'center',
          }}
        >
          <input
            type="text"
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            placeholder="AAPL"
            disabled={pageState === 'analyzing'}
            maxLength={5}
            style={{
              width: 120,
              padding: '10px 14px',
              border: '1.5px solid #D1D5DB',
              borderRadius: 8,
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: 16,
              fontWeight: 700,
              color: '#1A1A1A',
              background: pageState === 'analyzing' ? '#F9FAFB' : '#FFFFFF',
              outline: 'none',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          />

          <select
            value={queryMode}
            onChange={e => setQueryMode(e.target.value)}
            disabled={pageState === 'analyzing'}
            style={{
              padding: '10px 14px',
              border: '1.5px solid #D1D5DB',
              borderRadius: 8,
              fontFamily: 'Inter, sans-serif',
              fontSize: 13,
              color: '#374151',
              background: pageState === 'analyzing' ? '#F9FAFB' : '#FFFFFF',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="full_ic">Full IC — 5 analysts</option>
            <option value="quick_screen">Quick Screen</option>
            <option value="valuation">Valuation Focus</option>
            <option value="risk_check">Risk Check</option>
            <option value="macro_view">Macro View</option>
          </select>

          <button
            onClick={handleSubmit}
            disabled={pageState === 'analyzing' || !ticker.trim()}
            style={{
              padding: '10px 22px',
              background: pageState === 'analyzing' || !ticker.trim() ? '#E5E7EB' : '#1A1A1A',
              color: pageState === 'analyzing' || !ticker.trim() ? '#9CA3AF' : '#FFFFFF',
              border: 'none',
              borderRadius: 8,
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: 13,
              fontWeight: 700,
              cursor: pageState === 'analyzing' || !ticker.trim() ? 'not-allowed' : 'pointer',
              letterSpacing: '0.02em',
              transition: 'background 0.15s',
            }}
          >
            {pageState === 'analyzing' ? 'Analyzing...' : 'Run Analysis'}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              padding: '12px 16px',
              background: '#FFF1F2',
              border: '1px solid #FECDD3',
              borderRadius: 8,
              marginBottom: 24,
              fontSize: 13,
              color: '#9F1239',
              fontFamily: 'IBM Plex Mono, monospace',
            }}
          >
            Error: {error}
          </div>
        )}

        {/* Analyzing state */}
        {pageState === 'analyzing' && (
          <div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: '#10B981',
                  animation: 'pulse 1.4s ease-in-out infinite',
                }}
              />
              <span
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: 13,
                  color: '#374151',
                  flex: 1,
                }}
              >
                {statusLine || 'Running debate...'}
              </span>
              <button
                onClick={handleCancel}
                style={{
                  padding: '6px 14px',
                  background: 'transparent',
                  color: '#6B7280',
                  border: '1px solid #D1D5DB',
                  borderRadius: 6,
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: 11,
                  cursor: 'pointer',
                  letterSpacing: '0.02em',
                }}
              >
                Cancel analysis
              </button>
            </div>

            <div
              style={{
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                overflow: 'hidden',
                background: '#FFFFFF',
              }}
            >
              <div
                style={{
                  padding: '8px 16px',
                  borderBottom: '1px solid #E5E7EB',
                  background: '#F9FAFB',
                }}
              >
                <span
                  style={{
                    fontFamily: 'IBM Plex Mono, monospace',
                    fontSize: 10,
                    fontWeight: 700,
                    color: '#6B7280',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                  }}
                >
                  Agent Signals — Live
                </span>
              </div>
              {agents.map(card => (
                <AgentCardRow key={card.name} card={card} />
              ))}
            </div>
          </div>
        )}

        {/* Memo ready */}
        {pageState === 'memo_ready' && result && (() => {
          const memo = result.structured_memo;
          return (
            <div>
              <VerdictBanner
                verdict={result.verdict}
                confidence={result.confidence}
                ticker={activeTicker.current}
                onToggleReasoning={() => setShowReasoning(v => !v)}
                showReasoning={showReasoning}
              />

              {/* 2-column memo grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                <MemoSection title="Investment Thesis">
                  {memo.thesis
                    ? <p style={{ fontSize: 13, color: '#1A1A1A', lineHeight: 1.6, margin: 0 }}>{memo.thesis}</p>
                    : <Unavailable />}
                </MemoSection>

                <MemoSection title="Bear Case">
                  {memo.bear_case
                    ? <p style={{ fontSize: 13, color: '#1A1A1A', lineHeight: 1.6, margin: 0 }}>{memo.bear_case}</p>
                    : <Unavailable />}
                </MemoSection>

                <MemoSection title="Key Risks">
                  {memo.key_risks
                    ? (
                      <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
                        {memo.key_risks.map((risk, i) => (
                          <li
                            key={i}
                            style={{
                              display: 'flex',
                              gap: 8,
                              marginBottom: i < memo.key_risks!.length - 1 ? 8 : 0,
                              fontSize: 13,
                              color: '#374151',
                              lineHeight: 1.5,
                            }}
                          >
                            <span
                              style={{
                                flexShrink: 0,
                                fontFamily: 'IBM Plex Mono, monospace',
                                fontSize: 10,
                                fontWeight: 700,
                                color: '#DC2626',
                                background: '#FEF2F2',
                                padding: '2px 6px',
                                borderRadius: 4,
                                letterSpacing: '0.04em',
                                alignSelf: 'flex-start',
                                marginTop: 1,
                              }}
                            >
                              R{i + 1}
                            </span>
                            {risk}
                          </li>
                        ))}
                      </ul>
                    )
                    : <Unavailable />}
                </MemoSection>

                <MemoSection title="Valuation Range">
                  {memo.valuation_range
                    ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {(['bear', 'base', 'bull'] as const).map(scenario => {
                          const colors = {
                            bear: { label: '#DC2626', bg: '#FEF2F2' },
                            base: { label: '#6B7280', bg: '#F9FAFB' },
                            bull: { label: '#16A34A', bg: '#F0FDF4' },
                          };
                          const c = colors[scenario];
                          return (
                            <div
                              key={scenario}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '6px 10px',
                                background: c.bg,
                                borderRadius: 6,
                              }}
                            >
                              <span
                                style={{
                                  fontFamily: 'IBM Plex Mono, monospace',
                                  fontSize: 10,
                                  fontWeight: 700,
                                  color: c.label,
                                  textTransform: 'uppercase',
                                  letterSpacing: '0.06em',
                                }}
                              >
                                {scenario}
                              </span>
                              <span
                                style={{
                                  fontFamily: 'IBM Plex Mono, monospace',
                                  fontSize: 14,
                                  fontWeight: 700,
                                  color: c.label,
                                }}
                              >
                                {memo.valuation_range![scenario]}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )
                    : <Unavailable />}
                </MemoSection>
              </div>

              {/* Full-width: What Would Make This Wrong */}
              <div style={{ marginBottom: 24 }}>
                <MemoSection title="What Would Make This Wrong">
                  {memo.what_would_make_this_wrong
                    ? <p style={{ fontSize: 13, color: '#1A1A1A', lineHeight: 1.6, margin: 0 }}>{memo.what_would_make_this_wrong}</p>
                    : <Unavailable />}
                </MemoSection>
              </div>

              {/* Decision checklist */}
              <div
                style={{
                  border: '1.5px dashed #D1D5DB',
                  borderRadius: 8,
                  padding: 20,
                  marginBottom: 20,
                  background: '#FAFAFA',
                }}
              >
                <p
                  style={{
                    fontFamily: 'IBM Plex Mono, monospace',
                    fontSize: 10,
                    fontWeight: 700,
                    color: '#6B7280',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    margin: '0 0 16px',
                  }}
                >
                  Decision Checklist — required before saving
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {CHECKLIST_ITEMS.map((question, i) => (
                    <div key={i}>
                      <label
                        style={{
                          display: 'block',
                          fontSize: 12,
                          color: '#374151',
                          marginBottom: 4,
                          fontWeight: 500,
                        }}
                      >
                        {question}
                      </label>
                      <input
                        type="text"
                        value={checklist[i] || ''}
                        onChange={e => setChecklist(prev => ({ ...prev, [i]: e.target.value }))}
                        placeholder="Your answer..."
                        style={{
                          width: '100%',
                          padding: '8px 12px',
                          border: '1px solid #D1D5DB',
                          borderRadius: 6,
                          fontSize: 13,
                          color: '#1A1A1A',
                          background: '#FFFFFF',
                          outline: 'none',
                          boxSizing: 'border-box',
                          fontFamily: 'Inter, sans-serif',
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Save button */}
              <button
                onClick={handleSave}
                disabled={!allChecked}
                style={{
                  width: '100%',
                  padding: '12px 24px',
                  background: allChecked ? '#1A1A1A' : '#E5E7EB',
                  color: allChecked ? '#FFFFFF' : '#9CA3AF',
                  border: 'none',
                  borderRadius: 8,
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: allChecked ? 'pointer' : 'not-allowed',
                  letterSpacing: '0.02em',
                  marginBottom: 32,
                  transition: 'background 0.15s',
                }}
              >
                {copied ? 'Copied to clipboard' : 'Save Decision (copy to clipboard)'}
              </button>

              {/* Collapsible reasoning panel */}
              {showReasoning && (
                <div style={{ marginTop: 8 }}>
                  <div
                    style={{
                      border: '1px solid #E5E7EB',
                      borderRadius: 8,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        padding: '8px 16px',
                        borderBottom: '1px solid #E5E7EB',
                        background: '#F9FAFB',
                      }}
                    >
                      <span
                        style={{
                          fontFamily: 'IBM Plex Mono, monospace',
                          fontSize: 10,
                          fontWeight: 700,
                          color: '#6B7280',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                        }}
                      >
                        Full Agent Signals
                      </span>
                    </div>
                    {agents.map(card => (
                      <AgentCardRow key={card.name} card={{ ...card, done: true }} />
                    ))}
                  </div>

                  {result.debate_log.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div
                        style={{
                          border: '1px solid #E5E7EB',
                          borderRadius: 8,
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            padding: '8px 16px',
                            borderBottom: '1px solid #E5E7EB',
                            background: '#F9FAFB',
                          }}
                        >
                          <span
                            style={{
                              fontFamily: 'IBM Plex Mono, monospace',
                              fontSize: 10,
                              fontWeight: 700,
                              color: '#6B7280',
                              textTransform: 'uppercase',
                              letterSpacing: '0.08em',
                            }}
                          >
                            Debate Transcript ({result.debate_log.length} entries)
                          </span>
                        </div>
                        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                          {result.debate_log.map((entry, i) => (
                            <div
                              key={i}
                              style={{
                                padding: '10px 16px',
                                borderBottom: '1px solid #F3F4F6',
                                display: 'flex',
                                gap: 12,
                                alignItems: 'flex-start',
                              }}
                            >
                              <span
                                style={{
                                  fontFamily: 'IBM Plex Mono, monospace',
                                  fontSize: 10,
                                  color: '#9CA3AF',
                                  flexShrink: 0,
                                  marginTop: 2,
                                  minWidth: 60,
                                }}
                              >
                                R{entry.round} {entry.agent}
                              </span>
                              <p style={{ fontSize: 12, color: '#374151', margin: 0, lineHeight: 1.5 }}>
                                {entry.content}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })()}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.85); }
        }
      `}</style>
    </div>
  );
}
