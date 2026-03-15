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
    dcf: '📊',
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
    dcf: 'bg-blue-500',
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

export default api;
