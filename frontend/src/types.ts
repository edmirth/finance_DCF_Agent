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
}

export interface StreamEvent {
  type: 
    | 'start' | 'content' | 'token_delta' | 'end' | 'error' | 'thinking' | 'thought' | 'tool' | 'tool_result'
    | 'agent_finish' | 'phase_start' | 'search_query' | 'source_review' | 'phase_progress' | 'agent_thought'
    | 'plan_created' | 'plan_updated' | 'reflection' | 'ticker_metadata'
    // New streaming thinking events
    | 'thinking_start' | 'thinking_chunk' | 'thinking_end'
    | 'reflection_start' | 'reflection_chunk' | 'reflection_end';
  content?: string;
  agent?: string;
  error?: string;
  tool?: string;
  input?: string;
  ticker?: string; // Ticker detected from user query

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
}

export interface PortfolioHolding {
  id: string;
  ticker: string;
  shares: number;
  cost_basis: number;
}
