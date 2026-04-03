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
  project_id?: string;
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
  chart_type: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar' | 'pie' | 'table';
  ticker?: string;
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number | boolean>>;
  series?: ChartSeriesConfig[];
  x_key?: string;
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
  // table-only fields
  columns?: string[];
  rows?: string[][];
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
    | 'chart_data'
    // Arena (Investment Committee) events
    | 'arena_dispatch' | 'arena_agent_start' | 'arena_agent_done'
    | 'arena_conflict' | 'arena_synthesis'
    | 'arena_question' | 'arena_answer';
  content?: string;
  agent?: string;
  // Arena event fields
  view?: string;
  confidence?: number;
  reasoning?: string;
  consensus_score?: number;
  conviction_level?: string;
  next_action?: string;
  thesis_summary?: string;
  agents?: string[];
  query_mode?: string;
  description?: string;
  round?: number;
  from_agent?: string;
  to_agent?: string;
  question?: string;
  answer?: string;
  error?: string;
  tool?: string;
  input?: string;
  ticker?: string; // Ticker detected from user query

  // Chart data event fields (keep in sync with ChartDataEvent)
  id?: string;
  chart_type?: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar' | 'pie' | 'table';
  title?: string;
  subtitle?: string;
  data?: Array<Record<string, string | number | boolean>>;
  series?: ChartSeriesConfig[];
  x_key?: string;
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
  columns?: string[];
  rows?: string[][];

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

// ============================================================
// Project types
// ============================================================

export interface ProjectSummary {
  id: string;
  title: string;
  thesis: string;
  status: string;
  created_at: string;
  updated_at: string;
  session_count: number;
  document_count: number;
}

export interface ProjectConfig {
  tickers?: string[];
  preferred_agents?: string[];
}

export interface ProjectDetail extends ProjectSummary {
  config: ProjectConfig;
  memory_doc: string;
}

export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  uploaded_at: string;
}
