import { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import Chat from '../components/Chat';
import ToastNotification from '../components/ToastNotification';
import { Agent, Message, ProjectDetail, SessionSummary } from '../types';
import { getAgents, getProject, getProjectSessions, getSession } from '../api';

const AUTO_AGENT: Agent = {
  id: 'auto',
  name: 'Auto',
  description: 'Automatically routes to the best agent for your question',
  example: 'Ask anything about stocks, markets, or portfolio analysis',
  icon: '✨',
  color: 'bg-gray-500',
};

function ProjectWorkspace() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent>(AUTO_AGENT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Session restore
  const [restoredSessionId, setRestoredSessionId] = useState<string | undefined>(undefined);
  const [restoredMessages, setRestoredMessages] = useState<Message[] | undefined>(undefined);
  const [chatKey, setChatKey] = useState(0);

  // Project sessions list
  const [projectSessions, setProjectSessions] = useState<SessionSummary[]>([]);

  // Toast
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    loadData(projectId);
  }, [projectId]);

  // Update URL when a new session is saved
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

  // Reload project sessions after a session is saved
  useEffect(() => {
    const handler = () => {
      if (projectId) loadProjectSessions(projectId);
    };
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, [projectId]);

  const loadData = async (id: string) => {
    try {
      const [proj, fetchedAgents] = await Promise.all([
        getProject(id),
        getAgents(),
      ]);
      setProject(proj);
      const chatAgents = [AUTO_AGENT, ...fetchedAgents.filter(a => a.id !== 'portfolio' && a.id !== 'dcf')];
      setAgents(chatAgents);
      await loadProjectSessions(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project');
    } finally {
      setLoading(false);
    }
  };

  const loadProjectSessions = async (id: string) => {
    try {
      const sessions = await getProjectSessions(id);
      setProjectSessions(sessions);
    } catch {
      // non-fatal
    }
  };

  const restoreSession = async (sessionId: string) => {
    try {
      const session = await getSession(sessionId);
      setRestoredSessionId(sessionId);
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
      setChatKey(k => k + 1);
    } catch {
      setSearchParams({});
    }
  };

  const handleNewSession = useCallback(() => {
    setRestoredSessionId(undefined);
    setRestoredMessages(undefined);
    setSearchParams({});
    setChatKey(k => k + 1);
  }, [setSearchParams]);

  const handleAnalysisSaved = useCallback(() => {
    setShowToast(true);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen pl-20">
        <div className="text-center">
          <div className="flex justify-center gap-2 mb-4">
            <span className="loading-dot" />
            <span className="loading-dot" />
            <span className="loading-dot" />
          </div>
          <p style={{ fontFamily: 'Inter, sans-serif', color: '#9CA3AF', fontSize: '0.875rem' }}>
            Loading project...
          </p>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex items-center justify-center h-screen pl-20">
        <div className="text-center max-w-md px-6">
          <p style={{ fontFamily: 'Inter, sans-serif', color: '#6B7280' }}>
            {error || 'Project not found'}
          </p>
          <button
            onClick={() => navigate('/projects')}
            style={{
              marginTop: '1rem',
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.875rem',
              color: '#1A1A1A',
              background: 'none',
              border: '1px solid #E5E7EB',
              borderRadius: '0.5rem',
              padding: '0.5rem 1rem',
              cursor: 'pointer',
            }}
          >
            Back to Projects
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="pl-20 min-h-screen" style={{ background: '#FFFFFF' }}>
      {/* Project header */}
      <div
        style={{
          borderBottom: '1px solid #F3F4F6',
          padding: '1rem 1.5rem',
          background: '#FAFAFA',
        }}
      >
        <div className="flex items-start justify-between max-w-[1200px] mx-auto">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <button
                onClick={() => navigate('/projects')}
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.8125rem',
                  color: '#9CA3AF',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                Projects
              </button>
              <span style={{ color: '#D1D5DB', fontSize: '0.8125rem' }}>/</span>
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#6B7280' }}>
                {project.title}
              </span>
            </div>
            <h1 style={{ fontFamily: 'Inter, sans-serif', fontSize: '1.125rem', fontWeight: 600, color: '#1A1A1A', margin: 0 }}>
              {project.title}
            </h1>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.875rem', color: '#6B7280', marginTop: '0.25rem', maxWidth: '600px' }}>
              {project.thesis.length > 160 ? project.thesis.slice(0, 160) + '…' : project.thesis}
            </p>
          </div>
          <button
            onClick={handleNewSession}
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.8125rem',
              fontWeight: 500,
              color: '#FFFFFF',
              background: '#1A1A1A',
              border: 'none',
              borderRadius: '0.5rem',
              padding: '0.5rem 1rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            New session
          </button>
        </div>

        {/* Past sessions row */}
        {projectSessions.length > 0 && (
          <div className="max-w-[1200px] mx-auto" style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {projectSessions.slice(0, 8).map(s => (
              <button
                key={s.id}
                onClick={() => {
                  setSearchParams({ session: s.id });
                }}
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.75rem',
                  color: '#6B7280',
                  background: searchParams.get('session') === s.id ? '#F3F4F6' : '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: '1rem',
                  padding: '0.25rem 0.75rem',
                  cursor: 'pointer',
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {s.title || new Date(s.created_at).toLocaleDateString()}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Chat panel — full width, constrained */}
      <div className="flex justify-center items-start min-h-[calc(100vh-120px)]">
        <div className="w-full max-w-[720px] px-6 mx-auto">
          <Chat
            key={chatKey}
            agent={selectedAgent}
            agents={agents}
            onSelectAgent={setSelectedAgent}
            sessionId={restoredSessionId}
            initialMessages={restoredMessages}
            onAnalysisSaved={handleAnalysisSaved}
            projectId={projectId}
          />
        </div>
      </div>

      <ToastNotification
        message="Analysis saved to library"
        visible={showToast}
        onDismiss={() => setShowToast(false)}
      />
    </div>
  );
}

export default ProjectWorkspace;
