import { useState, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { BookOpen, FileText, Trash2, ChevronRight, ChevronLeft, BarChart2, Users, Menu, X } from 'lucide-react';
import { getSessions, deleteSession, getProjects } from '../api';
import { SessionSummary, ProjectSummary } from '../types';

const AGENT_TYPE_COLORS: Record<string, string> = {
  analyst: '#8B5CF6',
  earnings: '#F59E0B',
  graph: '#10B981',
  research: '#10B981',
  market: '#F97316',
  portfolio: '#6366F1',
  arena: '#10B981',
  auto: '#10B981',
};

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

function SessionRow({
  session,
  onDelete,
  onSelect,
}: {
  session: SessionSummary;
  onDelete: (id: string) => void;
  onSelect: (id: string) => void;
}) {
  const color = AGENT_TYPE_COLORS[session.agent_type] || '#9CA3AF';
  const label = AGENT_TYPE_LABELS[session.agent_type] || session.agent_type;
  const dateStr = new Date(session.last_active_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });

  return (
    <div
      onClick={() => onSelect(session.id)}
      className="group flex items-start gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition-colors duration-100 hover:bg-[#F7F7F5]"
    >
      {/* Colored dot indicator */}
      <div
        className="flex-shrink-0 mt-[5px]"
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: color,
          opacity: 0.7,
        }}
      />
      <div className="flex-1 min-w-0">
        <p
          className="text-[13px] font-medium text-slate-700 truncate leading-snug"
          title={session.title}
          style={{ letterSpacing: '-0.01em' }}
        >
          {session.title}
        </p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span
            style={{
              fontSize: '0.625rem',
              fontWeight: 500,
              color,
              letterSpacing: '0.01em',
              fontFamily: 'IBM Plex Mono, monospace',
            }}
          >
            {label}
          </span>
          <span className="text-slate-300">·</span>
          <span className="text-[10px] text-slate-400">{dateStr}</span>
        </div>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-50 text-slate-300 hover:text-red-400 transition-all duration-100 flex-shrink-0 mt-0.5"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

// Mobile header component with hamburger menu
function MobileHeader({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <div
      className="md:hidden fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4"
      style={{
        height: 56,
        background: '#FFFFFF',
        borderBottom: '1px solid #EBEBEB',
      }}
    >
      <div className="flex items-center gap-3">
        {/* Monogram mark */}
        <div
          className="flex-shrink-0 flex items-center justify-center"
          style={{
            width: 28,
            height: 28,
            background: '#0F172A',
            borderRadius: 7,
          }}
        >
          <span
            style={{
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: 13,
              fontWeight: 700,
              color: '#FFFFFF',
              letterSpacing: '-0.02em',
            }}
          >
            P
          </span>
        </div>
        <span
          style={{
            fontFamily: 'IBM Plex Sans, sans-serif',
            fontSize: 14,
            fontWeight: 600,
            color: '#0F172A',
            letterSpacing: '-0.02em',
          }}
        >
          Phronesis
        </span>
      </div>
      
      <button
        onClick={onMenuClick}
        className="flex items-center justify-center p-2 -mr-2 rounded-lg transition-colors hover:bg-slate-100"
        style={{ minWidth: 44, minHeight: 44 }}
        aria-label="Open menu"
      >
        <Menu className="w-5 h-5 text-slate-600" />
      </button>
    </div>
  );
}

// Mobile drawer overlay
function MobileDrawer({
  isOpen,
  onClose,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="md:hidden fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 transition-opacity"
        onClick={onClose}
      />
      
      {/* Drawer */}
      <div
        className="absolute left-0 top-0 h-full w-[280px] bg-white shadow-xl transform transition-transform"
        style={{
          animation: 'slideInLeft 0.2s ease-out',
        }}
      >
        {/* Close button */}
        <div className="flex items-center justify-between px-4" style={{ height: 56, borderBottom: '1px solid #F3F3F3' }}>
          <div className="flex items-center gap-3">
            <div
              className="flex-shrink-0 flex items-center justify-center"
              style={{
                width: 28,
                height: 28,
                background: '#0F172A',
                borderRadius: 7,
              }}
            >
              <span
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: 13,
                  fontWeight: 700,
                  color: '#FFFFFF',
                  letterSpacing: '-0.02em',
                }}
              >
                P
              </span>
            </div>
            <span
              style={{
                fontFamily: 'IBM Plex Sans, sans-serif',
                fontSize: 14,
                fontWeight: 600,
                color: '#0F172A',
                letterSpacing: '-0.02em',
              }}
            >
              Phronesis
            </span>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center p-2 -mr-2 rounded-lg transition-colors hover:bg-slate-100"
            style={{ minWidth: 44, minHeight: 44 }}
            aria-label="Close menu"
          >
            <X className="w-5 h-5 text-slate-600" />
          </button>
        </div>
        
        {children}
      </div>
    </div>
  );
}

function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem('sidebarCollapsed');
    return stored === 'true';
  });
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_projects, setProjects] = useState<ProjectSummary[]>([]);

  // Close mobile drawer on route change
  useEffect(() => {
    setIsMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    loadSessions();
    loadProjects();
    const interval = setInterval(() => {
      loadSessions();
      loadProjects();
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handler = () => loadSessions();
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, []);

  const loadSessions = async () => {
    try {
      const data = await getSessions(10);
      setSessions(data);
    } catch { /* ignore */ }
  };

  const loadProjects = async () => {
    try {
      const data = await getProjects();
      setProjects(data.filter((p: { status: string }) => p.status === 'active').slice(0, 5));
    } catch { /* ignore */ }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
    } catch { /* ignore */ }
  };

  const handleSelectSession = (id: string) => {
    navigate(`/?session=${id}`);
    setIsMobileOpen(false);
  };

  const toggleSidebar = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem('sidebarCollapsed', String(newState));
    window.dispatchEvent(new CustomEvent('sidebarToggle', { detail: { isCollapsed: newState } }));
  };

  // Shared navigation content
  const NavContent = ({ isMobile = false }: { isMobile?: boolean }) => (
    <>
      {/* Navigation */}
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden"
        style={{ padding: isMobile ? '12px 10px' : (isCollapsed ? '12px 8px' : '12px 10px') }}
      >
        {/* Primary nav links */}
        <div style={{ marginBottom: 4 }}>
          <NavItem
            to="/"
            end
            icon={<FileText className="w-4 h-4" />}
            label="Investment Memo"
            sub="IC memo · 5 analysts"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/earnings"
            icon={<BarChart2 className="w-4 h-4" />}
            label="Earnings"
            sub="Quarterly trends & transcript"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/arena"
            icon={<Users className="w-4 h-4" />}
            label="Arena"
            sub="Multi-agent debate mode"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/library"
            icon={<BookOpen className="w-4 h-4" />}
            label="Library"
            sub="Saved analyses"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
        </div>

        {/* Recent sessions */}
        {(isMobile || !isCollapsed) && sessions.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: '#C4C4C4',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                padding: '0 12px',
                marginBottom: 6,
                fontFamily: 'IBM Plex Mono, monospace',
              }}
            >
              Recent
            </div>
            <div>
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
              onClick={() => isMobile && setIsMobileOpen(false)}
              className="block mt-2 px-3 transition-colors duration-100"
              style={{
                fontSize: 11,
                color: '#10B981',
                textDecoration: 'none',
                fontWeight: 500,
                letterSpacing: '-0.01em',
              }}
            >
              View all →
            </NavLink>
          </div>
        )}

        {/* Empty state prompt */}
        {(isMobile || !isCollapsed) && sessions.length === 0 && (
          <div
            style={{
              marginTop: 20,
              padding: '14px',
              background: '#FAFAFA',
              borderRadius: 10,
              border: '1px solid #F0F0F0',
            }}
          >
            <p
              style={{
                fontSize: 12,
                color: '#9CA3AF',
                lineHeight: 1.6,
                margin: 0,
                fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            >
              Search a ticker to generate your first investment memo.
            </p>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div
        style={{
          padding: isMobile ? '12px 20px' : (isCollapsed ? '12px 0' : '12px 20px'),
          borderTop: '1px solid #F3F3F3',
          display: 'flex',
          alignItems: 'center',
          justifyContent: (isMobile || !isCollapsed) ? 'flex-start' : 'center',
          gap: 8,
          flexShrink: 0,
        }}
      >
        {(isMobile || !isCollapsed) ? (
          <span
            style={{
              fontSize: 10,
              color: '#D1D5DB',
              fontFamily: 'IBM Plex Mono, monospace',
              letterSpacing: '0.03em',
            }}
          >
            Powered by Claude
          </span>
        ) : (
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#10B981',
            }}
          />
        )}
      </div>
    </>
  );

  return (
    <>
      {/* Mobile header */}
      <MobileHeader onMenuClick={() => setIsMobileOpen(true)} />
      
      {/* Mobile drawer */}
      <MobileDrawer isOpen={isMobileOpen} onClose={() => setIsMobileOpen(false)}>
        <NavContent isMobile />
      </MobileDrawer>

      {/* Desktop sidebar - hidden on mobile */}
      <div
        className={`hidden md:flex fixed left-0 top-0 h-screen flex-col z-40 transition-all duration-300 ease-in-out ${isCollapsed ? 'w-[60px]' : 'w-[240px]'}`}
        style={{
          background: '#FFFFFF',
          borderRight: '1px solid #EBEBEB',
        }}
      >
        {/* Header / Logo */}
        <div
          className="flex items-center relative flex-shrink-0"
          style={{
            height: 60,
            padding: isCollapsed ? '0 0 0 16px' : '0 0 0 20px',
            borderBottom: '1px solid #F3F3F3',
          }}
        >
          <div className={`flex items-center gap-3 ${isCollapsed ? '' : ''}`}>
            {/* Monogram mark */}
            <div
              className="flex-shrink-0 flex items-center justify-center"
              style={{
                width: 28,
                height: 28,
                background: '#0F172A',
                borderRadius: 7,
              }}
            >
              <span
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: 13,
                  fontWeight: 700,
                  color: '#FFFFFF',
                  letterSpacing: '-0.02em',
                }}
              >
                P
              </span>
            </div>

            {!isCollapsed && (
              <div>
                <span
                  style={{
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: 14,
                    fontWeight: 600,
                    color: '#0F172A',
                    letterSpacing: '-0.02em',
                    display: 'block',
                  }}
                >
                  Phronesis
                </span>
                <span
                  style={{
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: 10,
                    fontWeight: 400,
                    color: '#9CA3AF',
                    letterSpacing: '0.02em',
                    display: 'block',
                    marginTop: 1,
                  }}
                >
                  Financial Intelligence
                </span>
              </div>
            )}
          </div>

          {/* Collapse toggle */}
          <button
            onClick={toggleSidebar}
            className="absolute -right-3 top-1/2 -translate-y-1/2 flex items-center justify-center transition-colors duration-150 hover:bg-slate-50"
            style={{
              width: 22,
              height: 22,
              background: '#FFFFFF',
              border: '1px solid #E5E7EB',
              borderRadius: '50%',
              color: '#9CA3AF',
              zIndex: 10,
            }}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed
              ? <ChevronRight className="w-3 h-3" />
              : <ChevronLeft className="w-3 h-3" />}
          </button>
        </div>

        <NavContent />
      </div>
    </>
  );
}

// Shared nav item component
function NavItem({
  to,
  end,
  icon,
  label,
  sub,
  isCollapsed,
  onClick,
}: {
  to: string;
  end?: boolean;
  icon: React.ReactNode;
  label: string;
  sub: string;
  isCollapsed: boolean;
  onClick?: () => void;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      title={isCollapsed ? label : undefined}
      style={{ textDecoration: 'none' }}
    >
      {({ isActive }) => (
        <div
          className="flex items-center gap-2.5 rounded-lg transition-colors duration-100"
          style={{
            padding: isCollapsed ? '8px 10px' : '10px 12px',
            marginBottom: 2,
            background: isActive ? '#F5F5F5' : 'transparent',
            cursor: 'pointer',
            justifyContent: isCollapsed ? 'center' : 'flex-start',
            minHeight: 44, // Touch-friendly
          }}
        >
          {/* Icon */}
          <div
            style={{
              color: isActive ? '#10B981' : '#ABABAB',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              transition: 'color 0.12s ease',
            }}
          >
            {icon}
          </div>

          {/* Label + subtitle */}
          {!isCollapsed && (
            <div className="flex-1 min-w-0 overflow-hidden">
              <span
                style={{
                  display: 'block',
                  fontSize: 13,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? '#0F172A' : '#6B7280',
                  letterSpacing: '-0.01em',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  lineHeight: 1.3,
                  transition: 'color 0.12s ease, font-weight 0.12s ease',
                }}
              >
                {label}
              </span>
              <span
                style={{
                  display: 'block',
                  fontSize: 10.5,
                  color: '#BEBEBE',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  marginTop: 1,
                  lineHeight: 1.2,
                }}
              >
                {sub}
              </span>
            </div>
          )}
        </div>
      )}
    </NavLink>
  );
}

export default Sidebar;
