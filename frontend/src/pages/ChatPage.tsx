import { useState, useEffect } from 'react';
import Chat from '../components/Chat';
import { Agent } from '../types';
import { getAgents } from '../api';

function ChatPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      const fetchedAgents = await getAgents();
      const chatAgents = fetchedAgents.filter(a => a.id !== 'portfolio' && a.id !== 'earnings' && a.id !== 'dcf');
      setAgents(chatAgents);
      setSelectedAgent(chatAgents.find(a => a.id === 'research') || chatAgents[0]);
    } catch (error) {
      console.error('Failed to load agents:', error);
      setError(error instanceof Error ? error.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="home-page flex items-center justify-center pl-20">
        <div className="text-center">
          <div className="flex justify-center gap-2 mb-4">
            <span className="loading-dot" />
            <span className="loading-dot" />
            <span className="loading-dot" />
          </div>
          <p style={{ fontFamily: 'Inter, sans-serif', color: '#9CA3AF', fontSize: '0.875rem' }}>
            Loading...
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="home-page flex items-center justify-center pl-20">
        <div className="text-center max-w-md px-6">
          <h1
            className="text-xl font-medium mb-3"
            style={{ fontFamily: 'Inter, sans-serif', color: '#1A1A1A' }}
          >
            Unable to connect
          </h1>
          <p
            className="mb-6"
            style={{ fontFamily: 'Inter, sans-serif', color: '#6B7280', fontSize: '0.9375rem', lineHeight: 1.6 }}
          >
            {error}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.875rem',
              fontWeight: 500,
              color: '#FFFFFF',
              background: '#1A1A1A',
              padding: '0.625rem 1.5rem',
              borderRadius: '0.5rem',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!selectedAgent) {
    return (
      <div className="home-page flex items-center justify-center pl-20">
        <p style={{ fontFamily: 'Inter, sans-serif', color: '#9CA3AF' }}>No agents available</p>
      </div>
    );
  }

  return (
    <div className="home-page pl-20">
      <main className="flex justify-center items-start min-h-screen">
        <div className="w-full max-w-[720px] px-6 mx-auto">
          <Chat
            agent={selectedAgent}
            agents={agents}
            onSelectAgent={setSelectedAgent}
          />
        </div>
      </main>
    </div>
  );
}

export default ChatPage;
