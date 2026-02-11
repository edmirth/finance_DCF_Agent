import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Home, Briefcase, Sparkles, ChevronLeft, ChevronRight, DollarSign } from 'lucide-react';

function Sidebar() {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem('sidebarCollapsed');
    return stored === 'true';
  });

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
      <nav className="flex-1 p-5 overflow-hidden">
        <div className="space-y-2">
          {!isCollapsed && (
            <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4" style={{ letterSpacing: '0.05em' }}>
              Tools
            </p>
          )}
          <NavLink
            to="/"
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
            to="/earnings"
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-4 py-3.5 rounded-2xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? 'text-slate-900'
                  : 'text-slate-700 hover:bg-slate-50'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Earnings Analyst' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-xl flex-shrink-0 transition-all duration-300 border-2 ${isActive ? 'bg-slate-100 text-slate-900 border-slate-300 shadow-sm' : 'bg-slate-50 text-slate-600 border-transparent group-hover:border-slate-200 group-hover:bg-white group-hover:shadow-sm'}`}>
                  <DollarSign className="w-4 h-4 transition-transform duration-300 group-hover:scale-110" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <div className="flex-1 overflow-hidden">
                    <span className="font-semibold text-sm block truncate transition-colors duration-300 group-hover:text-slate-900" style={{ letterSpacing: '-0.01em' }}>Earnings Analyst</span>
                    <p className="text-xs text-slate-400 mt-0.5 truncate font-light">Fast earnings research</p>
                  </div>
                )}
              </>
            )}
          </NavLink>

          <NavLink
            to="/portfolio"
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-4 py-3.5 rounded-2xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? 'text-slate-900'
                  : 'text-slate-700 hover:bg-slate-50'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Portfolio' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-xl flex-shrink-0 transition-all duration-300 border-2 ${isActive ? 'bg-slate-100 text-slate-900 border-slate-300 shadow-sm' : 'bg-slate-50 text-slate-600 border-transparent group-hover:border-slate-200 group-hover:bg-white group-hover:shadow-sm'}`}>
                  <Briefcase className="w-4 h-4 transition-transform duration-300 group-hover:scale-110" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <div className="flex-1 overflow-hidden">
                    <span className="font-semibold text-sm block truncate transition-colors duration-300 group-hover:text-slate-900" style={{ letterSpacing: '-0.01em' }}>Portfolio</span>
                    <p className="text-xs text-slate-400 mt-0.5 truncate font-light">Manage investments</p>
                  </div>
                )}
              </>
            )}
          </NavLink>
        </div>

        {/* Quick Info Card */}
        {!isCollapsed && (
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
