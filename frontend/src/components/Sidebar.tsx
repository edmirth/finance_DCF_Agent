import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { MessageSquare, Briefcase, Sparkles, ChevronLeft, ChevronRight } from 'lucide-react';

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
    <div className={`fixed left-0 top-0 h-screen bg-white border-r border-gray-200 flex flex-col shadow-sm transition-all duration-300 ease-in-out z-40 ${isCollapsed ? 'w-20' : 'w-72'}`}>
      {/* Logo/Header */}
      <div className="p-6 border-b border-gray-100 relative">
        <div className={`flex items-center gap-3 ${isCollapsed ? 'justify-center' : ''}`}>
          <div className="w-12 h-12 bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl flex items-center justify-center shadow-lg shadow-gray-900/30 flex-shrink-0">
            <span className="text-2xl font-bold text-white">P</span>
          </div>
          {!isCollapsed && (
            <div className="overflow-hidden">
              <h1 className="text-xl font-bold text-gray-900 whitespace-nowrap">Phronesis AI</h1>
              <p className="text-xs text-gray-500 font-medium whitespace-nowrap">Analysis Suite</p>
            </div>
          )}
        </div>

        {/* Toggle Button */}
        <button
          onClick={toggleSidebar}
          className="absolute -right-3 top-8 w-6 h-6 bg-white border border-gray-200 rounded-full flex items-center justify-center hover:bg-gray-50 transition-colors shadow-sm z-10"
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
          ) : (
            <ChevronLeft className="w-3.5 h-3.5 text-gray-600" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 overflow-hidden">
        <div className="space-y-1">
          {!isCollapsed && (
            <p className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Navigation
            </p>
          )}
          <NavLink
            to="/"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-900 shadow-sm'
                  : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Chat Analysts' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-lg flex-shrink-0 ${isActive ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600'}`}>
                  <MessageSquare className="w-4 h-4" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <>
                    <div className="flex-1 overflow-hidden">
                      <span className="font-semibold text-sm block truncate">Chat Analysts</span>
                      <p className="text-xs text-gray-500 mt-0.5 truncate">AI-powered analysis</p>
                    </div>
                    {isActive && (
                      <div className="w-1 h-8 bg-gray-900 rounded-full"></div>
                    )}
                  </>
                )}
              </>
            )}
          </NavLink>

          <NavLink
            to="/portfolio"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-900 shadow-sm'
                  : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'
              } ${isCollapsed ? 'justify-center' : ''}`
            }
            title={isCollapsed ? 'Portfolio' : ''}
          >
            {({ isActive }) => (
              <>
                <div className={`p-2 rounded-lg flex-shrink-0 ${isActive ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600'}`}>
                  <Briefcase className="w-4 h-4" strokeWidth={2} />
                </div>
                {!isCollapsed && (
                  <>
                    <div className="flex-1 overflow-hidden">
                      <span className="font-semibold text-sm block truncate">Portfolio</span>
                      <p className="text-xs text-gray-500 mt-0.5 truncate">Manage investments</p>
                    </div>
                    {isActive && (
                      <div className="w-1 h-8 bg-gray-900 rounded-full"></div>
                    )}
                  </>
                )}
              </>
            )}
          </NavLink>
        </div>

        {/* Quick Info Card */}
        {!isCollapsed && (
          <div className="mt-6 p-4 bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl border border-gray-200">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-gray-900" />
              <h3 className="text-sm font-semibold text-gray-900">AI Powered</h3>
            </div>
            <p className="text-xs text-gray-600 leading-relaxed">
              Get intelligent financial insights using advanced AI agents
            </p>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-100 bg-gray-50">
        {!isCollapsed ? (
          <div className="text-xs text-gray-500 space-y-1">
            <p className="font-medium text-gray-600">Powered by</p>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-white rounded-md text-gray-700 font-medium border border-gray-200">Claude</span>
              <span className="text-gray-400">•</span>
              <span className="px-2 py-0.5 bg-white rounded-md text-gray-700 font-medium border border-gray-200">GPT</span>
            </div>
          </div>
        ) : (
          <div className="flex justify-center">
            <Sparkles className="w-5 h-5 text-gray-900" />
          </div>
        )}
      </div>
    </div>
  );
}

export default Sidebar;
