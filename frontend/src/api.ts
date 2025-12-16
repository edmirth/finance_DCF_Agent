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

    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            onMessage(data as StreamEvent);
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  } catch (error: any) {
    onError(error.message || 'Failed to stream message');
  }
};

// Helper functions
const getAgentIcon = (agentId: string): string => {
  const icons: Record<string, string> = {
    dcf: '📊',
    analyst: '📈',
    research: '🔍',
    market: '🌐',
    portfolio: '💼',
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
  };
  return colors[agentId] || 'bg-gray-500';
};

export default api;
