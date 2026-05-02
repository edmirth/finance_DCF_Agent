import axios from 'axios';
import { Agent, ChatRequest, StreamEvent, SessionSummary, SessionDetail, AnalysisSummary, AnalysisDetail, WatchlistDetail, ProjectSummary, ProjectDetail, ProjectDocument } from './types';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getAgents = async (): Promise<Agent[]> => {
  const response = await api.get('/agents');
  return response.data.agents.map((agent: any) => ({
    ...agent,
    icon: getAgentIcon(agent.id),
    color: getAgentColor(agent.id),
  }));
};

export const getHealthStatus = async () => {
  const response = await api.get('/health');
  return response.data;
};

export const sendMessage = async (request: ChatRequest) => {
  const response = await api.post('/chat', request);
  return response.data;
};

export const streamMessage = async (
  request: ChatRequest,
  onMessage: (event: StreamEvent) => void,
  onError: (error: string) => void
): Promise<void> => {
  try {
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('No response body');
    }

    // Persistent buffer to handle SSE frames split across chunk boundaries
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      // Append new chunk to buffer
      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;

      // Split by newlines and process complete lines only
      const lines = buffer.split('\n');

      // Keep the last (potentially incomplete) line in buffer
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            onMessage(data as StreamEvent);
          } catch (e) {
            console.error('Failed to parse SSE data:', e, 'Line:', line);
          }
        }
      }
    }

    // Process any remaining data in buffer
    if (buffer.trim().startsWith('data: ')) {
      try {
        const data = JSON.parse(buffer.trim().slice(6));
        onMessage(data as StreamEvent);
      } catch (e) {
        console.error('Failed to parse final SSE data:', e);
      }
    }
  } catch (error: any) {
    onError(error.message || 'Failed to stream message');
  }
};

// Investment Memo streaming
export interface MemoEvent {
  type: string;
  [key: string]: any;
}

export const streamMemo = (
  ticker: string,
  queryMode: string = 'full_ic',
  onEvent: (event: MemoEvent) => void,
  onError: (error: string | null) => void
): { cancel: () => void } => {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/memo/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, query_mode: queryMode }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || `HTTP error ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No response body');

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent(data as MemoEvent);
            } catch (e) {
              onError('Analysis stream error — please try again');
              return;
            }
          }
        }
      }
      if (buffer.trim().startsWith('data: ')) {
        try {
          const data = JSON.parse(buffer.trim().slice(6));
          onEvent(data as MemoEvent);
        } catch (_) {
          onError('Analysis stream error — please try again');
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        onError(null); // user-initiated cancel — no error message
      } else {
        onError(error.message || 'Failed to stream memo');
      }
    }
  })();

  return { cancel: () => controller.abort() };
};

// Document upload
export const uploadDocument = async (file: File): Promise<{ filename: string; content: string; file_type: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await axios.post(`${API_BASE_URL}/upload-document`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

// Stock chart types
export interface StockQuote {
  symbol: string;
  name: string;
  exchange: string;
  price: number;
  changesPercentage: number;
  change: number;
  dayHigh: number;
  dayLow: number;
  yearHigh: number;
  yearLow: number;
  volume: number;
  avgVolume: number;
  marketCap: number;
  open: number;
  previousClose: number;
  pe?: number | null;
  eps?: number | null;
  beta?: number | null;
}

export interface ChartDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockChartData {
  ticker: string;
  quote: StockQuote;
  historical: ChartDataPoint[];
}

export interface ComparisonChartData {
  tickers: string[];
  quotes: Record<string, StockQuote>;
  historical: Record<string, ChartDataPoint[]>;
}

export type TimePeriod = '1M' | '6M' | 'YTD' | '1Y' | '5Y' | 'MAX';

export const getStockChart = async (
  ticker: string,
  period: TimePeriod = '1M'
): Promise<StockChartData> => {
  const response = await api.get(`/stock-chart/${ticker}`, {
    params: { period }
  });
  return response.data;
};

export const getStockChartComparison = async (
  tickers: string[],
  period: TimePeriod = '1M'
): Promise<ComparisonChartData> => {
  const response = await api.get('/stock-chart/compare', {
    params: { tickers: tickers.join(','), period }
  });
  return response.data;
};

// Helper functions
const getAgentIcon = (agentId: string): string => {
  const icons: Record<string, string> = {
    analyst: '📈',
    research: '🔍',
    market: '🌐',
    portfolio: '💼',
    earnings: '💰',
  };
  return icons[agentId] || '🤖';
};

const getAgentColor = (agentId: string): string => {
  const colors: Record<string, string> = {
    analyst: 'bg-purple-500',
    research: 'bg-green-500',
    market: 'bg-orange-500',
    portfolio: 'bg-indigo-500',
    earnings: 'bg-yellow-500',
  };
  return colors[agentId] || 'bg-gray-500';
};

// ============================================================
// Sessions (Chat History)
// ============================================================

export const getSessions = async (limit = 50): Promise<SessionSummary[]> => {
  const response = await api.get('/sessions', { params: { limit } });
  return response.data;
};

export const getSession = async (sessionId: string): Promise<SessionDetail> => {
  const response = await api.get(`/sessions/${sessionId}`);
  return response.data;
};

export const deleteSession = async (sessionId: string): Promise<void> => {
  await api.delete(`/sessions/${sessionId}`);
};

// ============================================================
// Analyses (Research Library)
// ============================================================

export interface AnalysisListParams {
  ticker?: string;
  tag?: string;
  q?: string;
  agent_type?: string;
}

export const getAnalyses = async (params?: AnalysisListParams): Promise<AnalysisSummary[]> => {
  const response = await api.get('/analyses', { params });
  return response.data;
};

export const getAnalysis = async (id: string): Promise<AnalysisDetail> => {
  const response = await api.get(`/analyses/${id}`);
  return response.data;
};

export const updateAnalysisTags = async (id: string, tags: string[]): Promise<{ id: string; tags: string[] }> => {
  const response = await api.patch(`/analyses/${id}`, { tags });
  return response.data;
};

export const exportAnalysis = (id: string): string => {
  // Returns a URL for direct browser download
  return `${API_BASE_URL}/analyses/${id}/export`;
};

export const deleteAnalysis = async (id: string): Promise<void> => {
  await api.delete(`/analyses/${id}`);
};

// ============================================================
// Watchlists
// ============================================================

export const getWatchlists = async (): Promise<WatchlistDetail[]> => {
  const response = await api.get('/watchlists');
  return response.data;
};

export const createWatchlist = async (name: string): Promise<{ id: string; name: string; created_at: string }> => {
  const response = await api.post('/watchlists', { name });
  return response.data;
};

export const addTickerToWatchlist = async (
  watchlistId: string,
  ticker: string,
  notes?: string
): Promise<{ id: string; ticker: string; notes: string | null; added_at: string }> => {
  const response = await api.post(`/watchlists/${watchlistId}/tickers`, { ticker, notes });
  return response.data;
};

export const removeTickerFromWatchlist = async (watchlistId: string, ticker: string): Promise<void> => {
  await api.delete(`/watchlists/${watchlistId}/tickers/${ticker}`);
};

export const deleteWatchlist = async (watchlistId: string): Promise<void> => {
  await api.delete(`/watchlists/${watchlistId}`);
};

// ============================================================
// Projects
// ============================================================

export const getProjects = async (): Promise<ProjectSummary[]> => {
  const response = await api.get('/projects');
  return response.data;
};

export const getProject = async (id: string): Promise<ProjectDetail> => {
  const response = await api.get(`/projects/${id}`);
  return response.data;
};

export const createProject = async (
  title: string,
  thesis: string,
  tickers?: string[]
): Promise<ProjectDetail> => {
  const response = await api.post('/projects', { title, thesis, tickers });
  return response.data;
};

export const updateProject = async (
  id: string,
  patch: Partial<{ title: string; thesis: string; config: Record<string, unknown>; status: string }>
): Promise<ProjectDetail> => {
  const response = await api.patch(`/projects/${id}`, patch);
  return response.data;
};

export const deleteProject = async (id: string): Promise<void> => {
  await api.delete(`/projects/${id}`);
};

export const uploadProjectDocument = async (
  projectId: string,
  file: File
): Promise<ProjectDocument> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await axios.post(`${API_BASE_URL}/projects/${projectId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const getProjectDocuments = async (projectId: string): Promise<ProjectDocument[]> => {
  const response = await api.get(`/projects/${projectId}/documents`);
  return response.data;
};

export const deleteProjectDocument = async (
  projectId: string,
  docId: string
): Promise<void> => {
  await api.delete(`/projects/${projectId}/documents/${docId}`);
};

export const getProjectMemory = async (id: string): Promise<string> => {
  const response = await api.get(`/projects/${id}/memory`);
  return response.data.memory_doc;
};

export const patchProjectMemory = async (id: string, memoryDoc: string): Promise<void> => {
  await api.patch(`/projects/${id}/memory`, { memory_doc: memoryDoc });
};

export const getProjectSessions = async (id: string): Promise<SessionSummary[]> => {
  const response = await api.get(`/projects/${id}/sessions`);
  return response.data;
};

// ============================================================
// Scheduled Agents
// ============================================================

export interface ScheduledAgentPayload {
  name: string;
  description?: string;
  template?: string;
  role_key?: string;
  tickers: string[];
  topics: string[];
  instruction: string;
  schedule_label: string;
  manager_agent_id?: string;
  delivery_email?: string;
  delivery_inapp: boolean;
}

export const getScheduledAgents = async () => {
  const response = await api.get('/scheduled-agents');
  return response.data.agents as import('./types').ScheduledAgent[];
};

export const createScheduledAgent = async (payload: ScheduledAgentPayload) => {
  const response = await api.post('/scheduled-agents', payload);
  return response.data as import('./types').ScheduledAgent;
};

export const getScheduledAgent = async (id: string) => {
  const response = await api.get(`/scheduled-agents/${id}`);
  return response.data as import('./types').ScheduledAgent;
};

export const updateScheduledAgent = async (id: string, patch: Partial<ScheduledAgentPayload & { is_active: boolean }>) => {
  const response = await api.patch(`/scheduled-agents/${id}`, patch);
  return response.data as import('./types').ScheduledAgent;
};

export const deleteScheduledAgent = async (id: string): Promise<void> => {
  await api.delete(`/scheduled-agents/${id}`);
};

export const triggerAgentRun = async (id: string): Promise<{ run_id: string; status: string }> => {
  const response = await api.post(`/scheduled-agents/${id}/run`);
  return response.data;
};

export const getAgentRuns = async (agentId: string, limit = 20) => {
  const response = await api.get(`/scheduled-agents/${agentId}/runs`, { params: { limit } });
  return response.data.runs as import('./types').AgentRun[];
};

export const getAgentRun = async (runId: string) => {
  const response = await api.get(`/agent-runs/${runId}`);
  return response.data as import('./types').AgentRun;
};

export const getHeartbeatRuns = async (agentId: string, limit = 20) => {
  const response = await api.get(`/scheduled-agents/${agentId}/heartbeat-runs`, { params: { limit } });
  return response.data.runs as import('./types').HeartbeatRun[];
};

export const getInbox = async (limit = 30, alertLevel?: string) => {
  const response = await api.get('/inbox', { params: { limit, alert_level: alertLevel } });
  return response.data.items as import('./types').InboxItem[];
};

// ============================================================
// CIO (Chief Investment Officer) — persistent orchestrator
// ============================================================

export interface CioMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface CioAction {
  type: 'delegate' | 'propose_hire';
  // delegate fields
  agent_id?: string;
  agent_name?: string;
  reason?: string;
  // propose_hire fields
  role_key?: string;
  role_title?: string;
  name?: string;
  description?: string;
  template?: string;
  tickers?: string[];
  topics?: string[];
  instruction?: string;
  schedule_label?: string;
  manager_agent_id?: string;
  proposal_id?: string;
  proposal_status?: import('./types').HireProposalStatus;
}

export interface CioChatResponse {
  message: string;
  action?: CioAction | null;
}

export interface CioTaskReviewResponse extends CioChatResponse {
  task_id: string;
}

export interface CeoInstructionDoc {
  key: string;
  filename: string;
  title: string;
  content: string;
}

export interface CeoRecentIssue {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  ticker: string;
  notes: string | null;
  project_id: string | null;
  project_title: string | null;
  selected_agents: string[];
  assigned_agent_id: string | null;
  owner_agent_id: string | null;
  triggered_by: string;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
}

export interface CeoActiveTeamAgent {
  id: string;
  name: string;
  role_key?: string | null;
  role_title?: string | null;
  role_family?: string | null;
  template: string;
  tickers: string[];
  reports_to_label: string;
  schedule_label: string;
  last_run_at: string | null;
  last_run_summary: string | null;
}

export interface CeoAgentPageData {
  agent: {
    id: string;
    name: string;
    title: string;
    status: string;
    aliases: string[];
    model: string;
    profile_path: string;
    last_heartbeat_at: string | null;
    last_heartbeat_message: string | null;
    last_reviewed_task_id: string | null;
  };
  stats: {
    recent_issue_count: number;
    pending_hire_count: number;
    active_team_count: number;
  };
  recent_issues: CeoRecentIssue[];
  pending_hire_proposals: import('./types').HireProposal[];
  active_team: CeoActiveTeamAgent[];
  instructions: CeoInstructionDoc[];
}

export const cioChat = async (messages: CioMessage[]): Promise<CioChatResponse> => {
  const response = await api.post('/cio/chat', { messages });
  return response.data;
};

export const cioReviewTask = async (taskId: string): Promise<CioTaskReviewResponse> => {
  const response = await api.post(`/cio/review-task/${taskId}`);
  return response.data;
};

export const getCeoAgentPage = async (limit = 20): Promise<CeoAgentPageData> => {
  const response = await api.get('/cio/agent', { params: { limit } });
  return response.data;
};

export const updateCeoInstructionDoc = async (
  docKey: string,
  content: string,
): Promise<CeoInstructionDoc> => {
  const response = await api.put(`/cio/agent/instructions/${docKey}`, { content });
  return response.data;
};

export interface CeoHeartbeatResponse {
  status: string;
  message: string;
  task_id: string | null;
  task_title: string | null;
  action: CioAction | null;
  reviewed_at: string | null;
}

export const runCeoHeartbeat = async (): Promise<CeoHeartbeatResponse> => {
  const response = await api.post('/cio/agent/heartbeat');
  return response.data;
};

export const updateCeoAgentStatus = async (
  status: 'idle' | 'paused',
): Promise<{
  status: 'idle' | 'paused';
  last_heartbeat_at: string | null;
  last_heartbeat_message: string | null;
  last_reviewed_task_id: string | null;
}> => {
  const response = await api.put('/cio/agent/status', { status });
  return response.data;
};

export const cioDelegate = async (agentId: string): Promise<{ run_id: string; status: string; agent_name: string }> => {
  const response = await api.post(`/cio/delegate/${agentId}`);
  return response.data;
};

export const getHireProposals = async (status?: import('./types').HireProposalStatus) => {
  const response = await api.get('/cio/hire-proposals', { params: status ? { status } : undefined });
  return response.data.proposals as import('./types').HireProposal[];
};

export const createHireProposal = async (
  action: CioAction,
  deliveryInapp = true,
  deliveryEmail?: string
) => {
  const response = await api.post('/cio/hire-proposals', {
    action,
    delivery_inapp: deliveryInapp,
    delivery_email: deliveryEmail,
  });
  return response.data as import('./types').HireProposal;
};

export const approveHireProposal = async (
  proposalId: string,
  decisionNote?: string
): Promise<{
  proposal: import('./types').HireProposal;
  agent: { id: string; name: string; role_key?: string; role_title?: string; template: string; tickers: string[]; schedule_label: string; created_at: string };
}> => {
  const response = await api.post(`/cio/hire-proposals/${proposalId}/approve`, {
    decision_note: decisionNote,
  });
  return response.data;
};

export const rejectHireProposal = async (
  proposalId: string,
  decisionNote?: string
) => {
  const response = await api.post(`/cio/hire-proposals/${proposalId}/reject`, {
    decision_note: decisionNote,
  });
  return response.data as import('./types').HireProposal;
};

export const cioHire = async (
  action: CioAction,
  deliveryInapp = true,
  deliveryEmail?: string
): Promise<{
  proposal: import('./types').HireProposal;
  agent: { id: string; name: string; role_key?: string; role_title?: string; template: string; tickers: string[]; schedule_label: string; created_at: string };
}> => {
  const response = await api.post('/cio/hire', {
    action,
    delivery_inapp: deliveryInapp,
    delivery_email: deliveryEmail,
  });
  return response.data;
};

export interface MemoSavePayload {
  ticker: string;
  verdict: string;
  confidence: number;
  structured_memo: Record<string, unknown>;
  checklist_answers: {
    why_now: string;
    exit_condition: string;
    max_position_size: string;
    quarterly_check_metric: string;
  };
}

export const saveMemo = async (payload: MemoSavePayload): Promise<{ id: number; share_slug: string }> => {
  const response = await api.post('/api/memo/save', payload);
  return response.data;
};

// ─── Investment Mandate ─────────────────────────────────────────────────────

export interface InvestmentMandate {
  id?: string;
  firm_name: string;
  mandate_text: string;
  benchmark: string;
  target_return_pct: number;
  max_position_pct: number;
  max_sector_pct: number;
  max_portfolio_beta: number;
  max_drawdown_pct: number;
  strategy_style: string;
  investment_horizon: string;
  restricted_tickers: string[];
  updated_at?: string;
}

export const getMandate = async (): Promise<InvestmentMandate> => {
  const response = await api.get('/firm/mandate');
  return response.data;
};

export const updateMandate = async (
  patch: Partial<InvestmentMandate>
): Promise<InvestmentMandate> => {
  const response = await api.put('/firm/mandate', patch);
  return response.data;
};

// ─── Research Tasks (Phase 2 — the firm's "issue board") ────────────────────

export type TaskStatus = 'pending' | 'running' | 'in_review' | 'done' | 'cancelled' | 'failed';
export type TaskType =
  | 'initiate_coverage'
  | 'earnings'
  | 'thesis_update'
  | 'sector_screen'
  | 'risk_review'
  | 'ad_hoc';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';
export type GateStatus = 'not_run' | 'pending' | 'cleared' | 'blocked' | 'applied';
export type ApprovalStatus = 'not_required' | 'pending' | 'approved' | 'rejected';

export interface AgentFinding {
  title: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  confidence: number;
  key_points: string[];
  duration_seconds: number;
  error: string | null;
}

export type DecisionAction = 'BUY' | 'HOLD' | 'SELL';
export type Conviction = 'HIGH' | 'MEDIUM' | 'LOW';

export interface RiskVerdict {
  verdict: 'approved' | 'flagged' | 'vetoed';
  flags: string[];
  suggested_max_size_pct: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  avg_confidence: number;
}

export interface ComplianceVerdict {
  verdict: 'cleared' | 'blocked';
  reasons: string[];
  blocked_by: string | null;
}

export interface PmSynthesis {
  // Original (Phase 1) fields
  overall_sentiment: 'bullish' | 'bearish' | 'neutral';
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  summary: string;
  // Phase 3 — structured decision
  action?: DecisionAction;
  suggested_size_pct?: number;
  horizon?: string;
  conviction?: Conviction;
  requires_approval?: boolean;
  blocked?: boolean;
  rationale?: string;
  risk_verdict?: RiskVerdict;
  compliance_verdict?: ComplianceVerdict;
}

export interface ResearchTask {
  id: string;
  ticker: string;
  task_type: TaskType;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  selected_agents: string[];
  completed_agents: string[];
  findings: Record<string, AgentFinding>;
  pm_synthesis: PmSynthesis | null;
  overall_sentiment: 'bullish' | 'bearish' | 'neutral' | null;
  project_id: string | null;
  parent_task_id: string | null;
  owner_agent_id: string | null;
  assigned_agent_id: string | null;
  source_heartbeat_run_id: string | null;
  triggered_by: string;
  run_id: string | null;
  mandate_check: GateStatus;
  risk_check: GateStatus;
  compliance_check: GateStatus;
  approval_status: ApprovalStatus;
  notes: string | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
}

export interface TaskMessage {
  id: string;
  task_id: string;
  kind: 'chat' | 'activity';
  role: 'user' | 'assistant' | 'system';
  author_label: string;
  author_agent_id: string | null;
  content: string;
  metadata: Record<string, any>;
  created_at: string | null;
}

export interface TaskDocument {
  id: string;
  task_id: string;
  title: string;
  document_type: string;
  status: 'draft' | 'published';
  revision: number;
  content_md: string;
  created_by_agent_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskRelatedWork {
  parent_task: ResearchTask | null;
  sub_issues: ResearchTask[];
  same_project_issues: ResearchTask[];
}

export interface CreateTaskBody {
  ticker?: string;
  task_type?: TaskType;
  title?: string;
  priority?: TaskPriority;
  selected_agents?: string[];
  project_id?: string;
  parent_task_id?: string;
  owner_agent_id?: string;
  assigned_agent_id?: string;
  source_heartbeat_run_id?: string;
  notes?: string;
  triggered_by?: string;
}

export const listTasks = async (filters?: {
  status?: TaskStatus;
  ticker?: string;
  task_type?: TaskType;
  project_id?: string;
  agent_id?: string;
  limit?: number;
}): Promise<ResearchTask[]> => {
  const response = await api.get('/tasks', { params: filters });
  return response.data.tasks;
};

export const getTask = async (id: string): Promise<ResearchTask> => {
  const response = await api.get(`/tasks/${id}`);
  return response.data;
};

export const createTask = async (body: CreateTaskBody): Promise<ResearchTask> => {
  const response = await api.post('/tasks', body);
  return response.data;
};

export const listTaskMessages = async (
  taskId: string,
  kind?: 'chat' | 'activity',
): Promise<TaskMessage[]> => {
  const response = await api.get(`/tasks/${taskId}/messages`, { params: kind ? { kind } : undefined });
  return response.data.messages;
};

export const createTaskChatTurn = async (
  taskId: string,
  body: { content: string; agent_id?: string | null },
): Promise<{ user_message: TaskMessage; assistant_message: TaskMessage; action: any | null }> => {
  const response = await api.post(`/tasks/${taskId}/chat`, body);
  return response.data;
};

export const createTaskMessage = async (
  taskId: string,
  body: {
    kind?: 'chat' | 'activity';
    role?: 'user' | 'assistant' | 'system';
    author_label?: string;
    author_agent_id?: string | null;
    content: string;
    metadata?: Record<string, any>;
  },
): Promise<TaskMessage> => {
  const response = await api.post(`/tasks/${taskId}/messages`, body);
  return response.data;
};

export const listTaskDocuments = async (taskId: string): Promise<TaskDocument[]> => {
  const response = await api.get(`/tasks/${taskId}/documents`);
  return response.data.documents;
};

export const createTaskDocument = async (
  taskId: string,
  body: {
    title: string;
    content_md?: string;
    document_type?: string;
    status?: 'draft' | 'published';
    created_by_agent_id?: string | null;
  },
): Promise<TaskDocument> => {
  const response = await api.post(`/tasks/${taskId}/documents`, body);
  return response.data;
};

export const updateTaskDocument = async (
  taskId: string,
  documentId: string,
  body: Partial<{
    title: string;
    content_md: string;
    document_type: string;
    status: 'draft' | 'published';
  }>,
): Promise<TaskDocument> => {
  const response = await api.patch(`/tasks/${taskId}/documents/${documentId}`, body);
  return response.data;
};

export const deleteTaskDocument = async (taskId: string, documentId: string): Promise<void> => {
  await api.delete(`/tasks/${taskId}/documents/${documentId}`);
};

export const getTaskRelatedWork = async (taskId: string): Promise<TaskRelatedWork> => {
  const response = await api.get(`/tasks/${taskId}/related-work`);
  return response.data;
};

export const updateTask = async (
  id: string,
  patch: Partial<{
    status: TaskStatus;
    priority: TaskPriority;
    title: string;
    notes: string;
    project_id: string | null;
  }>,
): Promise<ResearchTask> => {
  const response = await api.patch(`/tasks/${id}`, patch);
  return response.data;
};

export const deleteTask = async (id: string): Promise<void> => {
  await api.delete(`/tasks/${id}`);
};

export const getTaskBoardStats = async (): Promise<Record<TaskStatus, number>> => {
  const response = await api.get('/tasks/stats/board');
  return response.data.counts;
};

export const runTaskPipeline = async (
  taskId: string,
): Promise<{ run_id: string; task_id: string; ticker: string }> => {
  const response = await api.post(`/tasks/${taskId}/run`);
  return response.data;
};

// ─── Firm Routines (Phase 4) ────────────────────────────────────────────────

export interface FirmRoutineCatalogItem {
  id: string;
  name: string;
  icon: string;
  description: string;
  schedule_label: string;
  schedule_human: string;
  template: string;
  default_instruction: string;
}

export interface InstalledRoutine {
  id: string;
  name: string;
  template: string;
  schedule_label: string;
  schedule_human?: string;
  tickers: string[];
  next_run_at: string | null;
  is_active: boolean;
}

export const getFirmRoutinesCatalog = async (): Promise<FirmRoutineCatalogItem[]> => {
  const response = await api.get('/firm/routines/catalog');
  return response.data.routines;
};

export const installFirmRoutine = async (
  catalogId: string,
  tickers: string[],
  instruction?: string,
  deliveryEmail?: string,
): Promise<InstalledRoutine> => {
  const response = await api.post('/firm/routines/install', {
    catalog_id: catalogId,
    tickers,
    instruction,
    delivery_email: deliveryEmail,
  });
  return response.data;
};

export default api;
