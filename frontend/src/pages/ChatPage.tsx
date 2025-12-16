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
      // Filter out portfolio agent from chat page
      const chatAgents = fetchedAgents.filter(a => a.id !== 'portfolio');
      setAgents(chatAgents);
      // Default to research assistant
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
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading Financial Analyst...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-bold text-red-600 mb-4">Error Loading App</h1>
          <p className="text-gray-700 mb-4">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!selectedAgent) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600">No agents available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-gray-50 to-gray-100">
      <div className="flex justify-center items-start min-h-screen pl-20 pr-0">
        <main className="w-full max-w-4xl px-8 py-8 mx-auto">
          {selectedAgent && (
            <Chat
              agent={selectedAgent}
              agents={agents}
              onSelectAgent={setSelectedAgent}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default ChatPage;
