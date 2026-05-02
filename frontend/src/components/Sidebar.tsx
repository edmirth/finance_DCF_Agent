import { useState, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  Bot,
  Briefcase,
  ChevronRight,
  ChevronLeft,
  CircleDot,
  FilePlus2,
  FolderOpen,
  Globe,
  Inbox,
  LayoutDashboard,
  Menu,
  PenTool,
  Repeat,
  Shield,
  Sparkles,
  TrendingUp,
  Workflow,
  X,
} from 'lucide-react';
import { getProjects, getScheduledAgents } from '../api';
import { roleMetaForAgent } from '../agentRoles';
import type { ProjectSummary, ScheduledAgent } from '../types';

const PROJECT_DOT_COLORS = ['#6366F1', '#8B5CF6', '#06B6D4', '#10B981', '#F59E0B', '#EC4899'];

function projectAccent(project: Pick<ProjectSummary, 'id' | 'title'>): string {
  const seed = `${project.id}:${project.title}`;
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return PROJECT_DOT_COLORS[hash % PROJECT_DOT_COLORS.length];
}

function agentSidebarIcon(agent: Pick<ScheduledAgent, 'role_key' | 'role_family' | 'template'>) {
  const meta = roleMetaForAgent(agent);
  const iconProps = { className: 'h-4 w-4' };

  switch (meta.family) {
    case 'portfolio':
      return <Briefcase {...iconProps} />;
    case 'macro':
      return <Globe {...iconProps} />;
    case 'risk':
      return <Shield {...iconProps} />;
    case 'event_driven':
      return <TrendingUp {...iconProps} />;
    case 'central_research':
      return <Sparkles {...iconProps} />;
    case 'monitoring':
      return <Bot {...iconProps} />;
    default:
      return <PenTool {...iconProps} />;
  }
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
  const [projectsExpanded, setProjectsExpanded] = useState(() => {
    const stored = localStorage.getItem('sidebarProjectsExpanded');
    return stored !== 'false';
  });
  const [agentsExpanded, setAgentsExpanded] = useState(() => {
    const stored = localStorage.getItem('sidebarAgentsExpanded');
    return stored !== 'false';
  });
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);

  // Close mobile drawer on route change
  useEffect(() => {
    setIsMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let cancelled = false;

    const loadSidebarData = async () => {
      try {
        const [projectRows, agentRows] = await Promise.all([
          getProjects(),
          getScheduledAgents(),
        ]);
        if (cancelled) return;
        setProjects(
          projectRows
            .filter((project) => project.status === 'active')
            .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
        );
        setAgents(
          agentRows
            .slice()
            .sort((a, b) => {
              if (a.is_active !== b.is_active) return Number(b.is_active) - Number(a.is_active);
              return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
            }),
        );
      } catch {
        if (!cancelled) {
          setProjects([]);
          setAgents([]);
        }
      }
    };

    loadSidebarData();
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  const toggleSidebar = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem('sidebarCollapsed', String(newState));
    window.dispatchEvent(new CustomEvent('sidebarToggle', { detail: { isCollapsed: newState } }));
  };

  const toggleProjectsExpanded = () => {
    setProjectsExpanded((current) => {
      const next = !current;
      localStorage.setItem('sidebarProjectsExpanded', String(next));
      return next;
    });
  };

  const toggleAgentsExpanded = () => {
    setAgentsExpanded((current) => {
      const next = !current;
      localStorage.setItem('sidebarAgentsExpanded', String(next));
      return next;
    });
  };

  const visibleProjects = projects.slice(0, 6);
  const visibleAgents = agents.slice(0, 8);
  const isLeaderAgentActive = location.pathname === '/agents/ceo' || location.pathname === '/cio';

  // Shared navigation content
  const NavContent = ({ isMobile = false }: { isMobile?: boolean }) => (
    <>
      {/* Navigation */}
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden"
        style={{ padding: isMobile ? '12px 10px' : (isCollapsed ? '12px 8px' : '12px 10px') }}
      >
        {(isMobile || !isCollapsed) && (
          <button
            type="button"
            onClick={() => {
              navigate('/issues?new=1');
              isMobile && setIsMobileOpen(false);
            }}
            className="mb-4 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            <FilePlus2 className="w-4 h-4" />
            New Issue
          </button>
        )}

        {/* Primary nav links */}
        <div style={{ marginBottom: 4 }}>
          <NavItem
            to="/"
            end
            icon={<LayoutDashboard className="w-4 h-4" />}
            label="Dashboard"
            sub="Agents · runs · approvals"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/inbox"
            icon={<Inbox className="w-4 h-4" />}
            label="Inbox"
            sub="Messages and reports from agents"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
        </div>

        {(isMobile || !isCollapsed) && (
          <div
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: '#C4C4C4',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              padding: '0 12px',
              marginTop: 20,
              marginBottom: 6,
              fontFamily: 'IBM Plex Mono, monospace',
            }}
          >
            Work
          </div>
        )}

        <div style={{ marginBottom: 4 }}>
          <NavItem
            to="/issues"
            icon={<CircleDot className="w-4 h-4" />}
            label="Issues"
            sub="Open work and new issue intake"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/routines"
            icon={<Repeat className="w-4 h-4" />}
            label="Routines"
            sub="Recurring workflows and schedules"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          {!isMobile && isCollapsed && (
            <>
              <NavItem
                to="/projects"
                icon={<FolderOpen className="w-4 h-4" />}
                label="Projects"
                sub="Project workspaces"
                isCollapsed
                onClick={() => setIsMobileOpen(false)}
              />
              <NavItem
                to="/org"
                icon={<Workflow className="w-4 h-4" />}
                label="Org"
                sub="Agent hierarchy"
                isCollapsed
                onClick={() => setIsMobileOpen(false)}
              />
            </>
          )}
        </div>

        {(isMobile || !isCollapsed) && (
          <>
            <div
              className="flex items-center justify-between"
              style={{
                padding: '0 12px',
                marginTop: 20,
                marginBottom: 6,
              }}
            >
              <button
                type="button"
                onClick={toggleProjectsExpanded}
                className="flex items-center gap-1.5 text-slate-400 transition hover:text-slate-600"
              >
                <ChevronRight
                  className="h-3.5 w-3.5 transition-transform duration-150"
                  style={{ transform: projectsExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                />
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: 'inherit',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    fontFamily: 'IBM Plex Mono, monospace',
                  }}
                >
                  Projects
                </span>
              </button>
              <button
                type="button"
                onClick={() => {
                  navigate('/projects?new=1');
                  isMobile && setIsMobileOpen(false);
                }}
                className="flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="New project"
              >
                <span className="text-base font-medium leading-none">+</span>
              </button>
            </div>

            {projectsExpanded && (
              <div style={{ marginBottom: 4 }}>
                {visibleProjects.length > 0 ? (
                  visibleProjects.map((project) => {
                    const isProjectActive = location.pathname === `/projects/${project.id}`;
                    const accent = projectAccent(project);
                    return (
                      <button
                        key={project.id}
                        type="button"
                        onClick={() => {
                          navigate(`/projects/${project.id}`);
                          isMobile && setIsMobileOpen(false);
                        }}
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition"
                        style={{
                          marginBottom: 2,
                          background: isProjectActive ? '#F5F5F5' : 'transparent',
                        }}
                      >
                        <span
                          style={{
                            width: 12,
                            height: 12,
                            borderRadius: '999px',
                            background: accent,
                            flexShrink: 0,
                          }}
                        />
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 500,
                            color: '#1F2937',
                            fontFamily: 'IBM Plex Sans, sans-serif',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {project.title}
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      navigate('/projects?new=1');
                      isMobile && setIsMobileOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-slate-400 transition hover:bg-slate-50 hover:text-slate-600"
                  >
                    <FolderOpen className="h-4 w-4" />
                    Create first project
                  </button>
                )}
              </div>
            )}
          </>
        )}

        {(isMobile || !isCollapsed) && (
          <>
            <div
              className="flex items-center justify-between"
              style={{
                padding: '0 12px',
                marginTop: 20,
                marginBottom: 6,
              }}
            >
              <button
                type="button"
                onClick={toggleAgentsExpanded}
                className="flex items-center gap-1.5 text-slate-400 transition hover:text-slate-600"
              >
                <ChevronRight
                  className="h-3.5 w-3.5 transition-transform duration-150"
                  style={{ transform: agentsExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                />
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: 'inherit',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    fontFamily: 'IBM Plex Mono, monospace',
                  }}
                >
                  Agents
                </span>
              </button>
              <button
                type="button"
                onClick={() => {
                  navigate('/routines/new');
                  isMobile && setIsMobileOpen(false);
                }}
                className="flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="New agent"
              >
                <span className="text-base font-medium leading-none">+</span>
              </button>
            </div>

            {agentsExpanded && (
              <div style={{ marginBottom: 4 }}>
                <button
                  type="button"
                  onClick={() => {
                    navigate('/agents/ceo');
                    isMobile && setIsMobileOpen(false);
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition"
                  style={{
                    marginBottom: 2,
                    background: isLeaderAgentActive ? '#F5F5F5' : 'transparent',
                  }}
                >
                  <span
                    style={{
                      color: '#0F172A',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Briefcase className="h-4 w-4" />
                  </span>
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color: '#1F2937',
                      fontFamily: 'IBM Plex Sans, sans-serif',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      flex: 1,
                    }}
                  >
                    CEO
                  </span>
                  <span
                    className="inline-flex items-center gap-1"
                    style={{
                      fontSize: 11,
                      fontWeight: 500,
                      color: '#2563EB',
                      fontFamily: 'IBM Plex Sans, sans-serif',
                      flexShrink: 0,
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '999px',
                        background: '#2563EB',
                      }}
                    />
                    Live
                  </span>
                </button>

                {visibleAgents.map((agent) => {
                  const isAgentActive = location.pathname === `/routines/${agent.id}` || location.pathname === `/scheduled-agents/${agent.id}`;
                  const meta = roleMetaForAgent(agent);
                  return (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => {
                        navigate(`/routines/${agent.id}`, { state: { from: '/' } });
                        isMobile && setIsMobileOpen(false);
                      }}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition"
                      style={{
                        marginBottom: 2,
                        background: isAgentActive ? '#F5F5F5' : 'transparent',
                      }}
                    >
                      <span
                        style={{
                          color: meta.color,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        {agentSidebarIcon(agent)}
                      </span>
                      <span
                        style={{
                          fontSize: 13,
                          fontWeight: 500,
                          color: '#1F2937',
                          fontFamily: 'IBM Plex Sans, sans-serif',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}
                      >
                        {agent.name}
                      </span>
                      {agent.is_active && (
                        <span
                          className="inline-flex items-center gap-1"
                          style={{
                            fontSize: 11,
                            fontWeight: 500,
                            color: '#2563EB',
                            fontFamily: 'IBM Plex Sans, sans-serif',
                            flexShrink: 0,
                          }}
                        >
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: '999px',
                              background: '#2563EB',
                            }}
                          />
                          Live
                        </span>
                      )}
                    </button>
                  );
                })}

                {visibleAgents.length === 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      navigate('/routines/new');
                      isMobile && setIsMobileOpen(false);
                    }}
                    className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-slate-400 transition hover:bg-slate-50 hover:text-slate-600"
                  >
                    <Bot className="h-4 w-4" />
                    Hire first analyst
                  </button>
                )}
              </div>
            )}
          </>
        )}

        {(isMobile || !isCollapsed) && (
          <>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: '#C4C4C4',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                padding: '0 12px',
                marginTop: 20,
                marginBottom: 6,
                fontFamily: 'IBM Plex Mono, monospace',
              }}
            >
              Company
            </div>

            <div style={{ marginBottom: 4 }}>
              <NavItem
                to="/org"
                icon={<Workflow className="w-4 h-4" />}
                label="Org"
                sub="Hierarchy and orchestration"
                isCollapsed={!isMobile && isCollapsed}
                onClick={() => isMobile && setIsMobileOpen(false)}
              />
            </div>
          </>
        )}

        {(isMobile || !isCollapsed) && (
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
              Create work from Issues, manage recurring workflows in Routines, keep project-specific work in Projects, and review hired agents from the sidebar.
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
