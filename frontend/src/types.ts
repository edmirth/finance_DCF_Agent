export interface ThinkingStep {
  id: string;
  type: 'thought' | 'tool' | 'tool_result';
  content?: string;
  tool?: string;
  input?: string;
  timestamp: Date;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  agentType?: string;
  thinkingSteps?: ThinkingStep[];
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
  type: 'start' | 'content' | 'end' | 'error' | 'thinking' | 'thought' | 'tool' | 'tool_result' | 'agent_finish';
  content?: string;
  agent?: string;
  error?: string;
  tool?: string;
  input?: string;
}

export interface PortfolioHolding {
  id: string;
  ticker: string;
  shares: number;
  cost_basis: number;
}
