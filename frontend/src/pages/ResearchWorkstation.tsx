import React, { useState, useRef, createRef } from 'react';
import AgentCard, { AgentMeta, AgentCardHandle } from '../components/research/AgentCard';
import AssignModal from '../components/research/AssignModal';

// ---------------------------------------------------------------------------
// Static metadata — mirrors backend AGENT_META
// ---------------------------------------------------------------------------

const AGENT_META: Record<string, AgentMeta> = {
  dcf: {
    title: 'DCF Valuation',
    role: 'FMP DCF engine · Bull / Base / Bear · Levered + Unlevered',
    tools: ['FMP Custom DCF', 'Financial Datasets AI', 'Macro rates'],
  },
  fundamental: {
    title: 'Fundamental Analysis',
    role: 'Revenue, margins, competitive moat, SEC filings',
    tools: ['Financial Datasets AI', 'SEC EDGAR', 'Tavily search'],
  },
  quant: {
    title: 'Quantitative Signals',
    role: 'Price momentum, volatility, relative performance vs market',
    tools: ['FMP price history', 'SPY benchmark', 'Analyst revisions'],
  },
  risk: {
    title: 'Risk Assessment',
    role: 'Leverage, debt structure, dilution risk, stress testing',
    tools: ['Financial Datasets AI', 'FMP multiples', 'SEC filings'],
  },
  macro: {
    title: 'Macro Environment',
    role: 'Interest rates, GDP, inflation, sector cycle positioning',
    tools: ['Fed rates API', 'Tavily macro search', 'Sector analysis'],
  },
  sentiment: {
    title: 'Market Sentiment',
    role: 'News flow, insider activity, institutional ownership',
    tools: ['SEC Form 4', 'Tavily news', '13F filings'],
  },
};

const AGENT_KEYS = Object.keys(AGENT_META);

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const ResearchWorkstation: React.FC = () => {
  // Which agent card is currently being assigned (modal open)
  const [assigningAgent, setAssigningAgent] = useState<string | null>(null);

  // Stable refs for each card — created once
  const cardRefs = useRef<Record<string, React.RefObject<AgentCardHandle>>>(
    Object.fromEntries(AGENT_KEYS.map(k => [k, createRef<AgentCardHandle>()]))
  );

  const handleRun = (ticker: string, title: string, description: string) => {
    if (!assigningAgent) return;
    cardRefs.current[assigningAgent]?.current?.triggerRun(ticker, title, description);
    setAssigningAgent(null);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: '#FFFFFF',
      padding: '40px 48px 80px',
      fontFamily: 'IBM Plex Sans, sans-serif',
    }}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 36 }}>
        <h1 style={{
          fontSize: 22, fontWeight: 700, color: '#0F172A',
          margin: '0 0 6px', letterSpacing: '-0.025em',
        }}>
          Research Workstation
        </h1>
        <p style={{ fontSize: 13, color: '#9CA3AF', margin: 0, lineHeight: 1.5 }}>
          Click any analyst card to assign it to a stock and run it independently.
          Multiple analysts can run in parallel.
        </p>
      </div>

      {/* ── Agent grid ─────────────────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 16,
        alignItems: 'start',
        maxWidth: 1040,
      }}>
        {AGENT_KEYS.map(key => (
          <AgentCard
            key={key}
            ref={cardRefs.current[key]}
            agentKey={key}
            meta={AGENT_META[key]}
            onAssign={() => setAssigningAgent(key)}
          />
        ))}
      </div>

      {/* ── Hint footer ────────────────────────────────────────────────── */}
      <p style={{
        marginTop: 40, fontSize: 11, color: '#E5E7EB',
        fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '0.03em',
      }}>
        Powered by FMP · Financial Datasets AI · SEC EDGAR · Anthropic Claude
      </p>

      {/* ── Assignment modal ───────────────────────────────────────────── */}
      {assigningAgent && (
        <AssignModal
          agentKey={assigningAgent}
          agentTitle={AGENT_META[assigningAgent].title}
          onRun={handleRun}
          onClose={() => setAssigningAgent(null)}
        />
      )}
    </div>
  );
};

export default ResearchWorkstation;
