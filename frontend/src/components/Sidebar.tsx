import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Home, Sparkles, ChevronLeft, ChevronRight, BookOpen, MessageSquare, Trash2, Folder, FileText } from 'lucide-react';
import { getSessions, deleteSession, getProjects } from '../api';
import { SessionSummary, ProjectSummary } from '../types';

const AGENT_TYPE_LABELS: Record<string, string> = {
  analyst: 'Analyst',
  earnings: 'Earnings',
  graph: 'Graph',
  research: 'Research',
  market: 'Market',
  portfolio: 'Portfolio',
  arena: 'Arena',
  auto: 'Auto',
};

const AGENT_TYPE_COLORS: Record<string, string> = {
  analyst: '#8B5CF6',
  earnings: '#F59E0B',
  graph: '#10B981',
  research: '#10B981',
  market: '#F97316',
  portfolio: '#6366F1',
  arena: '#10B981',
  auto: '#6B7280',
};

function SessionRow({
  session,
  onDelete,
  onSelect,
}: {
  session: SessionSummary;
  onDelete: (id: string) => void;
  onSelect: (id: string) => void;
}) {
  const color = AGENT_TYPE_COLORS[session.agent_type] || '#6B7280';
  const label = AGENT_TYPE_LABELS[session.agent_type] || session.agent_type;
  const dateStr = new Date(session.last_active_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete(session.id);
  };

  return (
    <div
      onClick={() => onSelect(session.id)}
      className="group flex items-start gap-2 px-3 py-2 rounded-xl hover:bg-slate-50 cursor-pointer transition-all duration-150"
    >
      <MessageSquare className="w-3.5 h-3.5 text-slate-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p
          className="text-xs font-medium text-slate-700 truncate leading-tight"
          title={session.title}
          style={{ letterSpacing: '-0.01em' }}
        >
          {session.title}
        </p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span
            style={{
              fontSize: '0.625rem',
              fontWeight: 600,
              color,
              background: `${color}14`,
              padding: '1px 5px',
              borderRadius: '4px',
              letterSpacing: '0.02em',
            }}
          >
            {label}
          </span>
          <span className="text-slate-400" style={{ fontSize: '0.625rem' }}>
            {dateStr}
          </span>
        </div>
      </div>
      <button
        onClick={handleDelete}
        className="opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-all duration-150 flex-shrink-0"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

function Sidebar() {
  const navigate = useNavigate();
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem('sidebarCollapsed');
    return stored === 'true';
  });
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  useEffect(() => {
    loadSessions();
    loadProjects();
    // Refresh sessions and projects every 30 seconds
    const interval = setInterval(() => {
      loadSessions();
      loadProjects();
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  // Listen for a custom event so Chat can trigger a refresh after saving
  useEffect(() => {
    const handler = () => loadSessions();
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, []);

  const loadSessions = async () => {
    try {
      const data = await getSessions(10);
      setSessions(data);
    } catch {
      // ignore — backend might not be up yet
    }
  };

  const loadProjects = async () => {
    try {
      const data = await getProjects();
      setProjects(data.filter(p => p.status === 'active').slice(0, 5));
    } catch {
      // ignore — backend might not be up yet
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
    } catch {
      // ignore
    }
  };

  const handleSelectSession = (id: string) => {
    navigate(`/?session=${id}`);
  };

  const toggleSidebar = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem('sidebarCollapsed', String(newState));

    // Emit custom event for App component
    const event = new CustomEvent('sidebarToggle', {
      detail: { isCollapsed: newState }
    });
    window.dispatchEvent(event);
  };

  return (
    <div className={`fixed left-0 top-0 h-screen glass-effect border-r border-slate-200/80 flex flex-col shadow-2xl transition-all duration-300 ease-in-out z-40 ${isCollapsed ? 'w-20' : 'w-80'}`}>
      {/* Logo/Header */}
      <div className="p-6 border-b border-slate-200/60 relative">
        <div className={`flex items-center gap-3.5 ${isCollapsed ? 'justify-center' : ''}`}>
          <div className="relative w-12 h-12 flex-shrink-0">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-600 to-blue-700 rounded-xl transform rotate-3 opacity-20"></div>
            <div className="relative w-full h-full bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl flex items-center justify-center shadow-lg shadow-slate-900/30">
              <span className="text-2xl font-bold text-white" style={{ letterSpacing: '-0.02em' }}>P</span>
            </div>
          </div>
          {!isCollapsed && (
            <div className="overflow-hidden">
              <h1 className="text-xl font-semibold text-slate-900 whitespace-nowrap" style={{ letterSpacing: '-0.02em' }}>Phronesis AI</h1>
              <p className="text-xs text-slate-500 font-medium whitespace-nowrap mt-0.5">Financial Intelligence</p>
            </div>
          )}
        </div>

        {/* Toggle Button */}
        <button
          onClick={toggleSidebar}
          className="absolute -right-3 top-8 w-7 h-7 glass-effect border border-slate-200 rounded-full flex items-center justify-center hover:bg-slate-50 hover:shadow-md transition-all duration-200 shadow-sm z-10"
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-slate-600" />
          ) : (
            <ChevronLeft className="w-4 h-4 text-slate-600" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-5 overflow-y-auto overflow-x-hidden">
        <div className="space-y-2">
          {!isCollapsed && (
            <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4" style={{ letterSpacing: '0.05em' }}>
              Tools
            </p>
          )}
          <NavLink
            to="/"
            end
            onClick={() => window.dispatchEvent(new CustomEvent('newChat'))}
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-4 py-3.5 rounded-2xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? 'text-slate-900'
                  : 'text-slate-700 hover:bg-slate-50'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Home' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-xl flex-shrink-0 transition-all duration-300 border-2 ${isActive ? 'bg-slate-100 text-slate-900 border-slate-300 shadow-sm' : 'bg-slate-50 text-slate-600 border-transparent group-hover:border-slate-200 group-hover:bg-white group-hover:shadow-sm'}`}>
                  <Home className="w-4 h-4 transition-transform duration-300 group-hover:scale-110" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <div className="flex-1 overflow-hidden">
                    <span className="font-semibold text-sm block truncate transition-colors duration-300 group-hover:text-slate-900" style={{ letterSpacing: '-0.01em' }}>Home</span>
                    <p className="text-xs text-slate-400 mt-0.5 truncate font-light">AI-powered analysis</p>
                  </div>
                )}
              </>
            )}
          </NavLink>


          <NavLink
            to="/library"
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-4 py-3.5 rounded-2xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? 'text-slate-900'
                  : 'text-slate-700 hover:bg-slate-50'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Library' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-xl flex-shrink-0 transition-all duration-300 border-2 ${isActive ? 'bg-slate-100 text-slate-900 border-slate-300 shadow-sm' : 'bg-slate-50 text-slate-600 border-transparent group-hover:border-slate-200 group-hover:bg-white group-hover:shadow-sm'}`}>
                  <BookOpen className="w-4 h-4 transition-transform duration-300 group-hover:scale-110" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <div className="flex-1 overflow-hidden">
                    <span className="font-semibold text-sm block truncate transition-colors duration-300 group-hover:text-slate-900" style={{ letterSpacing: '-0.01em' }}>Library</span>
                    <p className="text-xs text-slate-400 mt-0.5 truncate font-light">Saved analyses</p>
                  </div>
                )}
              </>
            )}
          </NavLink>

          <NavLink
            to="/memo"
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-4 py-3.5 rounded-2xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? 'text-slate-900'
                  : 'text-slate-700 hover:bg-slate-50'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Investment Memo' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-xl flex-shrink-0 transition-all duration-300 border-2 ${isActive ? 'bg-slate-100 text-slate-900 border-slate-300 shadow-sm' : 'bg-slate-50 text-slate-600 border-transparent group-hover:border-slate-200 group-hover:bg-white group-hover:shadow-sm'}`}>
                  <FileText className="w-4 h-4 transition-transform duration-300 group-hover:scale-110" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <div className="flex-1 overflow-hidden">
                    <span className="font-semibold text-sm block truncate transition-colors duration-300 group-hover:text-slate-900" style={{ letterSpacing: '-0.01em' }}>Memo</span>
                    <p className="text-xs text-slate-400 mt-0.5 truncate font-light">IC investment memo</p>
                  </div>
                )}
              </>
            )}
          </NavLink>

          <NavLink
            to="/projects"
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-4 py-3.5 rounded-2xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? 'text-slate-900'
                  : 'text-slate-700 hover:bg-slate-50'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Projects' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-xl flex-shrink-0 transition-all duration-300 border-2 ${isActive ? 'bg-slate-100 text-slate-900 border-slate-300 shadow-sm' : 'bg-slate-50 text-slate-600 border-transparent group-hover:border-slate-200 group-hover:bg-white group-hover:shadow-sm'}`}>
                  <Folder className="w-4 h-4 transition-transform duration-300 group-hover:scale-110" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <div className="flex-1 overflow-hidden">
                    <span className="font-semibold text-sm block truncate transition-colors duration-300 group-hover:text-slate-900" style={{ letterSpacing: '-0.01em' }}>Projects</span>
                    <p className="text-xs text-slate-400 mt-0.5 truncate font-light">Thesis workspaces</p>
                  </div>
                )}
              </>
            )}
          </NavLink>
        </div>

        {/* Projects Section */}
        {!isCollapsed && projects.length > 0 && (
          <div className="mt-6">
            <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3" style={{ letterSpacing: '0.05em' }}>
              Projects
            </p>
            <div className="space-y-0.5">
              {projects.map(project => (
                <NavLink
                  key={project.id}
                  to={`/projects/${project.id}`}
                  className="group flex items-start gap-2 px-3 py-2 rounded-xl hover:bg-slate-50 cursor-pointer transition-all duration-150"
                >
                  <Folder className="w-3.5 h-3.5 text-emerald-500 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-xs font-medium text-slate-700 truncate leading-tight"
                      title={project.title}
                      style={{ letterSpacing: '-0.01em' }}
                    >
                      {project.title}
                    </p>
                    <p
                      className="text-slate-400 mt-0.5 truncate"
                      style={{ fontSize: '0.625rem' }}
                      title={project.thesis}
                    >
                      {project.thesis.slice(0, 60)}{project.thesis.length > 60 ? '…' : ''}
                    </p>
                  </div>
                </NavLink>
              ))}
            </div>
            <NavLink
              to="/projects"
              className="block mt-3 px-3 text-xs text-emerald-600 hover:text-emerald-700 font-medium transition-colors duration-150"
              style={{ letterSpacing: '-0.01em' }}
            >
              View all projects →
            </NavLink>
          </div>
        )}

        {/* Recent Conversations */}
        {!isCollapsed && sessions.length > 0 && (
          <div className="mt-6">
            <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3" style={{ letterSpacing: '0.05em' }}>
              Recent
            </p>
            <div className="space-y-0.5">
              {sessions.map(session => (
                <SessionRow
                  key={session.id}
                  session={session}
                  onDelete={handleDeleteSession}
                  onSelect={handleSelectSession}
                />
              ))}
            </div>
            <NavLink
              to="/library"
              className="block mt-3 px-3 text-xs text-emerald-600 hover:text-emerald-700 font-medium transition-colors duration-150"
              style={{ letterSpacing: '-0.01em' }}
            >
              View all analyses →
            </NavLink>
          </div>
        )}

        {/* Quick Info Card */}
        {!isCollapsed && sessions.length === 0 && (
          <div className="mt-6 p-5 glass-effect rounded-2xl border border-slate-200/80 shadow-lg">
            <div className="flex items-center gap-2.5 mb-2.5">
              <div className="p-1.5 bg-gradient-to-br from-gold-400 to-gold-500 rounded-lg shadow-md">
                <Sparkles className="w-3.5 h-3.5 text-white" />
              </div>
              <h3 className="text-sm font-semibold text-slate-900" style={{ letterSpacing: '-0.01em' }}>AI Powered</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed font-light">
              Get intelligent financial insights using advanced AI agents
            </p>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className="p-5 border-t border-slate-200/60 glass-effect">
        {!isCollapsed ? (
          <div className="text-xs text-slate-500 space-y-2">
            <p className="font-medium text-slate-600" style={{ letterSpacing: '0.01em' }}>Powered by</p>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-2.5 py-1 glass-effect rounded-lg text-slate-700 font-medium border border-slate-200/80 shadow-sm">Claude</span>
              <span className="text-slate-400">•</span>
              <span className="px-2.5 py-1 glass-effect rounded-lg text-slate-700 font-medium border border-slate-200/80 shadow-sm">GPT</span>
            </div>
          </div>
        ) : (
          <div className="flex justify-center">
            <div className="p-2 bg-gradient-to-br from-gold-400 to-gold-500 rounded-lg shadow-md">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Sidebar;
