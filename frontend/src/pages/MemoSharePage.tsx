import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';

// ─── Types ────────────────────────────────────────────────────────────────────

interface SharedMemo {
  ticker: string;
  verdict: 'BUY' | 'WATCH' | 'PASS';
  confidence: number;
  structured_memo: {
    thesis: string | null;
    bear_case: string | null;
    key_risks: string[] | null;
    valuation_range: { bear: string; base: string; bull: string } | null;
    what_would_make_this_wrong: string | null;
  };
  checklist_answers: {
    why_now: string;
    exit_condition: string;
    max_position_size: string;
    quarterly_check_metric: string;
  } | null;
  created_at: string | null;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const VERDICT_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  BUY:   { bg: '#F0FDF4', text: '#15803D', border: '#16A34A' },
  WATCH: { bg: '#FFFBEB', text: '#92400E', border: '#D97706' },
  PASS:  { bg: '#FFF1F2', text: '#9F1239', border: '#E11D48' },
};

const SCENARIO_COLORS: Record<string, { label: string }> = {
  bear: { label: '#DC2626' },
  base: { label: '#374151' },
  bull: { label: '#16A34A' },
};

// ─── Sub-components ────────────────────────────────────────────────────────────

function MemoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
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
            textTransform: 'uppercase' as const,
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MemoSharePage() {
  const { slug } = useParams<{ slug: string }>();
  const [memo, setMemo] = useState<SharedMemo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    fetch(`/api/m/${slug}`)
      .then(r => {
        if (!r.ok) throw new Error(r.status === 404 ? 'Memo not found' : 'Failed to load memo');
        return r.json();
      })
      .then(setMemo)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return (
      <div style={{ maxWidth: 720, margin: '80px auto', padding: '0 24px', textAlign: 'center', fontFamily: 'IBM Plex Mono, monospace', color: '#6B7280', fontSize: 13 }}>
        Loading memo...
      </div>
    );
  }

  if (error || !memo) {
    return (
      <div style={{ maxWidth: 720, margin: '80px auto', padding: '0 24px', textAlign: 'center', fontFamily: 'IBM Plex Mono, monospace', color: '#9F1239', fontSize: 13 }}>
        {error || 'Memo not found'}
      </div>
    );
  }

  const vs = VERDICT_STYLES[memo.verdict] || VERDICT_STYLES.WATCH;
  const m = memo.structured_memo;
  const date = memo.created_at ? new Date(memo.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) : null;

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#FFFFFF',
        fontFamily: 'Inter, -apple-system, sans-serif',
        color: '#1A1A1A',
      }}
    >
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '48px 24px 80px' }}>

        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 22, fontWeight: 700, color: '#1A1A1A', margin: '0 0 4px', letterSpacing: '-0.02em' }}>
            Investment Memo — {memo.ticker}
          </h1>
          {date && (
            <p style={{ fontSize: 12, color: '#9CA3AF', margin: 0 }}>Generated {date}</p>
          )}
        </div>

        {/* Verdict banner */}
        <div
          style={{
            padding: '16px 20px',
            background: vs.bg,
            border: `1.5px solid ${vs.border}`,
            borderRadius: 8,
            marginBottom: 24,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <span
            style={{
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: 20,
              fontWeight: 700,
              color: vs.text,
              letterSpacing: '0.04em',
            }}
          >
            {memo.verdict}
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ flex: 1, height: 6, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${Math.round(memo.confidence * 100)}%`, height: '100%', background: vs.border, borderRadius: 3 }} />
              </div>
              <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 12, color: vs.text, fontWeight: 600 }}>
                {Math.round(memo.confidence * 100)}% consensus
              </span>
            </div>
          </div>
        </div>

        {/* 2-column memo grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <MemoSection title="Investment Thesis">
            {m.thesis ? <p style={{ fontSize: 13, color: '#1A1A1A', lineHeight: 1.6, margin: 0 }}>{m.thesis}</p> : <Unavailable />}
          </MemoSection>

          <MemoSection title="Bear Case">
            {m.bear_case ? <p style={{ fontSize: 13, color: '#1A1A1A', lineHeight: 1.6, margin: 0 }}>{m.bear_case}</p> : <Unavailable />}
          </MemoSection>

          <MemoSection title="Key Risks">
            {m.key_risks
              ? (
                <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
                  {m.key_risks.map((risk, i) => (
                    <li key={i} style={{ display: 'flex', gap: 8, marginBottom: i < m.key_risks!.length - 1 ? 8 : 0 }}>
                      <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 10, color: '#9CA3AF', marginTop: 2, flexShrink: 0 }}>
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>{risk}</span>
                    </li>
                  ))}
                </ul>
              )
              : <Unavailable />}
          </MemoSection>

          <MemoSection title="Valuation Range">
            {m.valuation_range
              ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(['bear', 'base', 'bull'] as const).map(scenario => {
                    const c = SCENARIO_COLORS[scenario];
                    return (
                      <div key={scenario} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 10, fontWeight: 700, color: c.label, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                          {scenario}
                        </span>
                        <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 14, fontWeight: 700, color: c.label }}>
                          {m.valuation_range![scenario]}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )
              : <Unavailable />}
          </MemoSection>
        </div>

        {/* What Would Make This Wrong */}
        <div style={{ marginBottom: 24 }}>
          <MemoSection title="What Would Make This Wrong">
            {m.what_would_make_this_wrong
              ? <p style={{ fontSize: 13, color: '#1A1A1A', lineHeight: 1.6, margin: 0 }}>{m.what_would_make_this_wrong}</p>
              : <Unavailable />}
          </MemoSection>
        </div>

        {/* Checklist answers (read-only) */}
        {memo.checklist_answers && (
          <div
            style={{
              border: '1.5px dashed #D1D5DB',
              borderRadius: 8,
              padding: 20,
              background: '#FAFAFA',
            }}
          >
            <p style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 10, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 16px' }}>
              Decision Checklist
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {[
                ['Why now?', memo.checklist_answers.why_now],
                ['What would make you exit?', memo.checklist_answers.exit_condition],
                ['Max position size', memo.checklist_answers.max_position_size],
                ['Metric to check next quarter', memo.checklist_answers.quarterly_check_metric],
              ].map(([q, a], i) => (
                <div key={i}>
                  <p style={{ fontSize: 11, color: '#6B7280', fontWeight: 600, margin: '0 0 3px' }}>{q}</p>
                  <p style={{ fontSize: 13, color: '#1A1A1A', margin: 0 }}>{a}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <p style={{ marginTop: 32, fontSize: 11, color: '#D1D5DB', textAlign: 'center', fontFamily: 'IBM Plex Mono, monospace' }}>
          Generated by Investment Memo — AI investment committee analysis
        </p>
      </div>
    </div>
  );
}
