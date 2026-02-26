import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import Chat from '../components/Chat';
import ToastNotification from '../components/ToastNotification';
import { Agent, Message } from '../types';
import { getAgents, getSession, getWatchlists, createWatchlist, addTickerToWatchlist } from '../api';

// Virtual "Auto" agent — routes each message to the best specialized agent
const AUTO_AGENT: Agent = {
  id: 'auto',
  name: 'Auto',
  description: 'Automatically routes to the best agent for your question',
  example: 'Ask anything about stocks, markets, or portfolio analysis',
  icon: '✨',
  color: 'bg-gray-500',
};

function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Session restore
  const [restoredSessionId, setRestoredSessionId] = useState<string | undefined>(undefined);
  const [restoredMessages, setRestoredMessages] = useState<Message[] | undefined>(undefined);

  // Watchlist
  const [watchlistTickers, setWatchlistTickers] = useState<string[]>([]);
  const [defaultWatchlistId, setDefaultWatchlistId] = useState<string | null>(null);

  // Toast
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    loadAgents();
    loadWatchlists();
  }, []);

  // Update URL when a new session is saved (so it can be bookmarked / restored)
  useEffect(() => {
    const handler = (e: Event) => {
      const sid = (e as CustomEvent).detail?.sessionId;
      if (sid && !searchParams.get('session')) {
        setSearchParams({ session: sid }, { replace: true });
      }
    };
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, [searchParams, setSearchParams]);

  // Session restore from URL
  useEffect(() => {
    const sessionId = searchParams.get('session');
    if (sessionId) {
      restoreSession(sessionId);
    }
  }, [searchParams]);

  const loadAgents = async () => {
    try {
      const fetchedAgents = await getAgents();
      const chatAgents = [
        AUTO_AGENT,
        ...fetchedAgents.filter(a => a.id !== 'portfolio' && a.id !== 'dcf'),
      ];
      setAgents(chatAgents);
      setSelectedAgent(AUTO_AGENT); // Default to Auto mode
    } catch (error) {
      console.error('Failed to load agents:', error);
      setError(error instanceof Error ? error.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  };

  const loadWatchlists = async () => {
    try {
      const wls = await getWatchlists();
      if (wls.length === 0) {
        // Create a default watchlist on first load
        const wl = await createWatchlist('My Watchlist');
        setDefaultWatchlistId(wl.id);
        setWatchlistTickers([]);
      } else {
        const first = wls[0];
        setDefaultWatchlistId(first.id);
        setWatchlistTickers(first.tickers.map(t => t.ticker));
      }
    } catch {
      // ignore — backend might not have watchlists yet
    }
  };

  const restoreSession = async (sessionId: string) => {
    try {
      const session = await getSession(sessionId);
      setRestoredSessionId(sessionId);
      // Convert DB messages to frontend Message format
      const msgs: Message[] = session.messages.map(m => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: new Date(m.created_at),
        agentType: m.agent_type ?? undefined,
        ticker: m.ticker ?? undefined,
        followUps: m.follow_ups,
        thinkingSteps: [],
      }));
      setRestoredMessages(msgs);
    } catch {
      // If session not found, clear the param
      setSearchParams({});
    }
  };

  const handleAddWatchlistTicker = useCallback(async (ticker: string) => {
    if (!defaultWatchlistId) return;
    try {
      await addTickerToWatchlist(defaultWatchlistId, ticker);
      setWatchlistTickers(prev => prev.includes(ticker) ? prev : [...prev, ticker]);
    } catch {
      // Duplicate or other error — ignore silently
    }
  }, [defaultWatchlistId]);

  const handleWatchlistChipClick = useCallback((_ticker: string) => {
    // Chat.tsx handles chip click directly by calling sendToAgent
  }, []);

  const handleAnalysisSaved = useCallback(() => {
    setShowToast(true);
  }, []);

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
            sessionId={restoredSessionId}
            initialMessages={restoredMessages}
            watchlistTickers={watchlistTickers}
            onWatchlistChipClick={handleWatchlistChipClick}
            onAddWatchlistTicker={handleAddWatchlistTicker}
            onAnalysisSaved={handleAnalysisSaved}
          />
        </div>
      </main>

      {/* Save toast */}
      <ToastNotification
        message="Analysis saved to library"
        visible={showToast}
        onDismiss={() => setShowToast(false)}
      />
    </div>
  );
}

export default ChatPage;
