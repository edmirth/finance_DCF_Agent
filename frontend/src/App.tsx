import { useState, useEffect } from 'react';
import Chat from './components/Chat';
import { Agent } from './types';
import { getAgents } from './api';

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      const fetchedAgents = await getAgents();
      setAgents(fetchedAgents);
      // Default to research assistant
      setSelectedAgent(fetchedAgents.find(a => a.id === 'research') || fetchedAgents[0]);
    } catch (error) {
      console.error('Failed to load agents:', error);
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Main Chat */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {selectedAgent && (
          <Chat
            agent={selectedAgent}
            agents={agents}
            onSelectAgent={setSelectedAgent}
          />
        )}
      </main>
    </div>
  );
}

export default App;
