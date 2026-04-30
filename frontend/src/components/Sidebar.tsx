import { useState, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { BookOpen, FilePlus2, FileText, ChevronRight, ChevronLeft, BarChart2, Menu, X, LayoutDashboard, BrainCircuit, Users, FolderOpen } from 'lucide-react';

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

  // Close mobile drawer on route change
  useEffect(() => {
    setIsMobileOpen(false);
  }, [location.pathname]);

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
        {(isMobile || !isCollapsed) && (
          <button
            type="button"
            onClick={() => {
              navigate('/?new=1');
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
            sub="Issue board · PM-first workflow"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/cio"
            icon={<BrainCircuit className="w-4 h-4" />}
            label="PM"
            sub="Issue review · staffing & delegation"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/team"
            icon={<Users className="w-4 h-4" />}
            label="Team"
            sub="Approved roster & proposals"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/projects"
            icon={<FolderOpen className="w-4 h-4" />}
            label="Projects"
            sub="Thesis workspaces & documents"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/research"
            icon={<LayoutDashboard className="w-4 h-4" />}
            label="Research"
            sub="Parallel analyst workstation"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
          <NavItem
            to="/memo"
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
            to="/library"
            icon={<BookOpen className="w-4 h-4" />}
            label="Library"
            sub="Saved analyses"
            isCollapsed={!isMobile && isCollapsed}
            onClick={() => isMobile && setIsMobileOpen(false)}
          />
        </div>

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
              Start with the PM to frame the work and let the system decide what coverage to add.
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
