export interface ThinkingStep {
  id: string;
  type: 
    | 'thought' | 'tool' | 'tool_result' | 'phase_start' | 'search_query' | 'source_review' 
    | 'phase_progress' | 'agent_thought' | 'plan_created' | 'plan_updated' | 'reflection'
    // New streaming thinking events
    | 'thinking_start' | 'thinking_chunk' | 'thinking_end'
    | 'reflection_start' | 'reflection_chunk' | 'reflection_end';
  content?: string;
  tool?: string;
  input?: string;
  timestamp: Date;

  // Fields for enhanced reasoning
  phase?: 'gathering_data' | 'searching' | 'reviewing' | 'analyzing' | 'calculating' | 'synthesizing' | 'reasoning';
  searchQuery?: string;
  source?: {
    title: string;
    domain: string;
    url?: string;
    type?: 'financial_data' | 'web_search' | 'news' | 'calculation';
  };
  progress?: {
    current: number;
    total: number;
    description: string;
  };
  summary?: {
    key: string;
    value: string;
  }[];
  plan?: string[];  // Array of plan steps
  
  // Streaming thinking text (accumulated from thinking_chunk events)
  thinkingText?: string;
  // Streaming reflection text (accumulated from reflection_chunk events)
  reflectionText?: string;
  // Whether this thinking block is currently streaming
  isStreaming?: boolean;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  agentType?: string;
  thinkingSteps?: ThinkingStep[];
  ticker?: string; // Ticker extracted from query metadata
  followUps?: string[]; // Follow-up questions generated after response
  routedAgent?: string; // Which agent auto-routing selected (e.g. 'analyst')
  isAutoRouted?: boolean; // Whether this message was handled via auto-routing
  chartsById?: Record<string, ChartDataEvent>;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  example: string;
  icon: string;
  color: string;
}

export interface ChatRequest {
  message: string;
  agent_type: string;
  model: string;
  session_id?: string;
  is_followup?: boolean;
}

export interface ChartSeriesConfig {
  key: string;
  label: string;
  type: 'bar' | 'line';
  color: string;
  yAxis?: 'left' | 'right';
  colorByField?: string;
  colorIfTrue?: string;
  colorIfFalse?: string;
}

export interface ChartDataEvent {
  type: 'chart_data';
  id: string;
  chart_type: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar';
  ticker?: string;
  title: string;
  data: Array<Record<string, string | number | boolean>>;
  series: ChartSeriesConfig[];
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
}

export interface StreamEvent {
  type:
    | 'start' | 'content' | 'token_delta' | 'end' | 'error' | 'thinking' | 'thought' | 'tool' | 'tool_result'
    | 'agent_finish' | 'phase_start' | 'search_query' | 'source_review' | 'phase_progress' | 'agent_thought'
    | 'plan_created' | 'plan_updated' | 'reflection' | 'ticker_metadata'
    // New streaming thinking events
    | 'thinking_start' | 'thinking_chunk' | 'thinking_end'
    | 'reflection_start' | 'reflection_chunk' | 'reflection_end'
    // Earnings progress events
    | 'earnings_progress'
    // Follow-up questions
    | 'follow_ups'
    // Auto-routing decision
    | 'routing_decision'
    // Chart data events
    | 'chart_data';
  content?: string;
  agent?: string;
  error?: string;
  tool?: string;
  input?: string;
  ticker?: string; // Ticker detected from user query

  // Chart data event fields
  id?: string;
  chart_type?: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar';
  title?: string;
  data?: Array<Record<string, string | number | boolean>>;
  series?: ChartSeriesConfig[];
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;

  // Fields for enhanced events
  phase?: string;
  query?: string;
  source?: {
    title: string;
    domain: string;
    url?: string;
    type?: 'financial_data' | 'web_search' | 'news' | 'calculation';
  };
  progress?: {
    current: number;
    total: number;
    description: string;
  };
  plan?: string[];  // Array of plan steps for plan_created/plan_updated events

  // Earnings progress fields
  node?: string;
  status?: string;
  detail?: string;

  // Follow-up questions
  questions?: string[];
}

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  content: string;
  status: 'uploading' | 'ready' | 'error';
  error?: string;
}

export interface PortfolioHolding {
  id: string;
  ticker: string;
  shares: number;
  cost_basis: number;
}

export interface Citation {
  id: number;
  title: string;
  url?: string;
  type: 'financial_data' | 'web_search' | 'news' | 'calculation';
}

// ============================================================
// Persistence layer types
// ============================================================

export interface SessionSummary {
  id: string;
  title: string;
  agent_type: string;
  created_at: string;
  last_active_at: string;
}

export interface SessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agent_type: string | null;
  ticker: string | null;
  thinking_steps: any[];
  follow_ups: string[];
  created_at: string;
  chart_specs?: string | null;
}

export interface SessionDetail extends SessionSummary {
  messages: SessionMessage[];
}

export interface AnalysisSummary {
  id: string;
  ticker: string | null;
  agent_type: string;
  title: string;
  content_preview: string;
  tags: string[];
  session_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisDetail extends Omit<AnalysisSummary, 'content_preview'> {
  content: string;
}

export interface WatchlistTicker {
  id: string;
  ticker: string;
  notes: string | null;
  added_at: string;
}

export interface WatchlistDetail {
  id: string;
  name: string;
  created_at: string;
  tickers: WatchlistTicker[];
}
