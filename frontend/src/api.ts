import axios from 'axios';
import { Agent, ChatRequest, StreamEvent } from './types';

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

// Stock chart types
export interface StockQuote {
  symbol: string;
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

export type TimePeriod = '1D' | '1W' | '1M' | '3M' | '1Y' | 'ALL';

export const getStockChart = async (
  ticker: string,
  period: TimePeriod = '1M'
): Promise<StockChartData> => {
  const response = await api.get(`/stock-chart/${ticker}`, {
    params: { period }
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

export default api;
