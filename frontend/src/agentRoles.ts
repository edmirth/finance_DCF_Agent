import type { AgentRoleKey, AgentTemplate, ScheduledAgent } from './types';

export interface AgentRoleMeta {
  key: AgentRoleKey;
  title: string;
  family: string;
  template: AgentTemplate;
  description: string;
  color: string;
  bg: string;
  letter: string;
  requiresTickers: boolean;
  instructionPlaceholder: string;
  instructionHint: string;
}

export const ROLE_DEFS: AgentRoleMeta[] = [
  {
    key: 'generalist_analyst',
    title: 'Generalist Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Generalist single-name coverage analyst for ad hoc equity work.',
    color: '#0F766E',
    bg: '#CCFBF1',
    letter: 'G',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover AAPL for the PM. Focus on moat durability, Services growth, margin support, and valuation vs the market.',
    instructionHint: 'What should this analyst own for the PM?',
  },
  {
    key: 'semis_analyst',
    title: 'Semis Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for semiconductors and adjacent hardware ecosystems.',
    color: '#0F766E',
    bg: '#CCFBF1',
    letter: 'S',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover NVDA, AMD, and TSM. Focus on AI demand, pricing power, supply bottlenecks, and hyperscaler capex.',
    instructionHint: 'Define the semiconductor coverage mandate.',
  },
  {
    key: 'software_analyst',
    title: 'Software Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for enterprise software and application businesses.',
    color: '#0284C7',
    bg: '#E0F2FE',
    letter: 'S',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover MSFT and NOW. Focus on seat growth, pricing, AI monetization, and renewal strength.',
    instructionHint: 'What software names and metrics matter?',
  },
  {
    key: 'financials_analyst',
    title: 'Financials Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for banks, insurers, asset managers, and exchanges.',
    color: '#0F766E',
    bg: '#D1FAE5',
    letter: 'F',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover JPM and SPGI. Focus on deposit trends, credit quality, fee resilience, and valuation relative to history.',
    instructionHint: 'Define the financials coverage mandate.',
  },
  {
    key: 'healthcare_analyst',
    title: 'Healthcare Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for healthcare, medtech, biotech, and pharma.',
    color: '#9333EA',
    bg: '#F3E8FF',
    letter: 'H',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover LLY and ISRG. Focus on pipeline durability, procedure growth, reimbursement, and competitive threats.',
    instructionHint: 'Define the healthcare coverage mandate.',
  },
  {
    key: 'consumer_analyst',
    title: 'Consumer Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for consumer internet, retail, and staples.',
    color: '#EA580C',
    bg: '#FFEDD5',
    letter: 'C',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover AMZN and COST. Focus on traffic, pricing power, unit economics, and demand elasticity.',
    instructionHint: 'Define the consumer coverage mandate.',
  },
  {
    key: 'industrials_analyst',
    title: 'Industrials Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for industrials, transports, and capital goods.',
    color: '#475569',
    bg: '#E2E8F0',
    letter: 'I',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover CAT and GE. Focus on backlog quality, cycle sensitivity, margins, and end-market demand.',
    instructionHint: 'Define the industrials coverage mandate.',
  },
  {
    key: 'energy_analyst',
    title: 'Energy Analyst',
    family: 'sector_coverage',
    template: 'fundamental_analyst',
    description: 'Sector analyst for energy, utilities, and commodity-linked names.',
    color: '#B45309',
    bg: '#FEF3C7',
    letter: 'E',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover XOM and SLB. Focus on commodity sensitivity, capital returns, and project economics.',
    instructionHint: 'Define the energy coverage mandate.',
  },
  {
    key: 'earnings_analyst',
    title: 'Earnings Analyst',
    family: 'event_driven',
    template: 'earnings_watcher',
    description: 'Event-driven analyst focused on earnings results, guidance, and call tone.',
    color: '#F59E0B',
    bg: '#FEF3C7',
    letter: 'E',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover AAPL into earnings. Focus on gross margin, China demand, and guidance credibility.',
    instructionHint: 'What earnings questions should this seat own?',
  },
  {
    key: 'portfolio_analyst',
    title: 'Portfolio Analyst',
    family: 'portfolio',
    template: 'portfolio_heartbeat',
    description: 'Cross-position analyst focused on portfolio health, concentration, and changes worth escalating.',
    color: '#8B5CF6',
    bg: '#EDE9FE',
    letter: 'P',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Watch the core portfolio. Flag concentration shifts, correlated drawdowns, and holdings with thesis deterioration.',
    instructionHint: 'What should this seat monitor across the book?',
  },
  {
    key: 'thesis_monitor',
    title: 'Thesis Monitor',
    family: 'monitoring',
    template: 'thesis_guardian',
    description: 'Monitoring seat focused on whether a thesis is strengthening or breaking.',
    color: '#10B981',
    bg: '#D1FAE5',
    letter: 'T',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Monitor our ASML thesis. Flag if order visibility weakens or customer capex plans are cut.',
    instructionHint: 'What thesis should this role defend or challenge?',
  },
  {
    key: 'quant_strategist',
    title: 'Quant Strategist',
    family: 'central_research',
    template: 'quant_analyst',
    description: 'Central desk quant for momentum, revisions, and factor behavior.',
    color: '#2563EB',
    bg: '#DBEAFE',
    letter: 'Q',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover NVDA and META. Watch revisions breadth, volatility regime changes, and relative strength vs sector peers.',
    instructionHint: 'What quantitative behavior should this role track?',
  },
  {
    key: 'risk_manager',
    title: 'Risk Manager',
    family: 'risk',
    template: 'risk_analyst',
    description: 'Independent risk seat focused on downside, leverage, and stress conditions.',
    color: '#DC2626',
    bg: '#FEE2E2',
    letter: 'R',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Watch TSLA and MSTR. Flag liquidity strain, dilution risk, and scenario asymmetry that would justify trimming.',
    instructionHint: 'What conditions should trigger risk escalation?',
  },
  {
    key: 'macro_strategist',
    title: 'Macro Strategist',
    family: 'macro',
    template: 'market_pulse',
    description: 'Cross-firm macro seat tracking policy, rates, inflation, and market regime.',
    color: '#7C3AED',
    bg: '#EDE9FE',
    letter: 'M',
    requiresTickers: false,
    instructionPlaceholder: 'e.g. Focus on the Fed path, AI capex sensitivity to rates, and the macro setup for cyclical vs defensive positioning.',
    instructionHint: 'What macro questions should this seat own?',
  },
  {
    key: 'market_narrative_analyst',
    title: 'Market Narrative Analyst',
    family: 'central_research',
    template: 'sentiment_analyst',
    description: 'Central seat for sentiment, positioning, and sell-side narrative shifts.',
    color: '#EA580C',
    bg: '#FFEDD5',
    letter: 'N',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. Cover META and NFLX. Track narrative inflections, estimate drift, analyst tone, and signs of crowded positioning.',
    instructionHint: 'What sentiment signals matter most?',
  },
];

export const ROLE_META_BY_KEY = Object.fromEntries(ROLE_DEFS.map((role) => [role.key, role])) as Record<AgentRoleKey, AgentRoleMeta>;

const TEMPLATE_FALLBACK_META: Partial<Record<AgentTemplate, Pick<AgentRoleMeta, 'title' | 'family' | 'color' | 'bg' | 'letter'>>> = {
  earnings_watcher: { title: 'Earnings Analyst', family: 'event_driven', color: '#F59E0B', bg: '#FEF3C7', letter: 'E' },
  market_pulse: { title: 'Macro Strategist', family: 'macro', color: '#7C3AED', bg: '#EDE9FE', letter: 'M' },
  thesis_guardian: { title: 'Thesis Monitor', family: 'monitoring', color: '#10B981', bg: '#D1FAE5', letter: 'T' },
  portfolio_heartbeat: { title: 'Portfolio Analyst', family: 'portfolio', color: '#8B5CF6', bg: '#EDE9FE', letter: 'P' },
  firm_pipeline: { title: 'Investment Pipeline', family: 'portfolio_management', color: '#334155', bg: '#E2E8F0', letter: 'I' },
  fundamental_analyst: { title: 'Generalist Analyst', family: 'sector_coverage', color: '#0F766E', bg: '#CCFBF1', letter: 'G' },
  quant_analyst: { title: 'Quant Strategist', family: 'central_research', color: '#2563EB', bg: '#DBEAFE', letter: 'Q' },
  risk_analyst: { title: 'Risk Manager', family: 'risk', color: '#DC2626', bg: '#FEE2E2', letter: 'R' },
  macro_analyst: { title: 'Macro Strategist', family: 'macro', color: '#7C3AED', bg: '#EDE9FE', letter: 'M' },
  sentiment_analyst: { title: 'Market Narrative Analyst', family: 'central_research', color: '#EA580C', bg: '#FFEDD5', letter: 'N' },
};

export function getRoleMeta(input: {
  role_key?: string | null;
  role_title?: string | null;
  template?: AgentTemplate | string | null;
}) {
  if (input.role_key && input.role_key in ROLE_META_BY_KEY) {
    const role = ROLE_META_BY_KEY[input.role_key as AgentRoleKey];
    return {
      ...role,
      displayTitle: input.role_title || role.title,
    };
  }

  const fallback = TEMPLATE_FALLBACK_META[input.template as AgentTemplate];
  return {
    key: (input.role_key || 'generalist_analyst') as AgentRoleKey,
    title: input.role_title || fallback?.title || String(input.template || 'Agent'),
    displayTitle: input.role_title || fallback?.title || String(input.template || 'Agent'),
    family: fallback?.family || 'custom',
    template: (input.template || 'market_pulse') as AgentTemplate,
    description: '',
    color: fallback?.color || '#64748B',
    bg: fallback?.bg || '#F1F5F9',
    letter: fallback?.letter || (input.role_title || String(input.template || 'A'))[0]?.toUpperCase() || 'A',
    requiresTickers: true,
    instructionPlaceholder: '',
    instructionHint: '',
  };
}

export function roleMetaForAgent(agent: Pick<ScheduledAgent, 'role_key' | 'role_title' | 'template'>) {
  return getRoleMeta({
    role_key: agent.role_key,
    role_title: agent.role_title,
    template: agent.template,
  });
}
