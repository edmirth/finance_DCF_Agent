import { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Portfolio from './pages/Portfolio';
import ProjectsListPage from './pages/ProjectsListPage';
import ProjectWorkspace from './pages/ProjectWorkspace';
import IssueDashboardPage from './pages/IssueDashboardPage';
import IssueDetailPage from './pages/IssueDetailPage';
import AgentsDashboard from './pages/AgentsDashboard';
import AgentSetupPage from './pages/AgentSetupPage';
import AgentDetailPage from './pages/AgentDetailPage';
import InboxPage from './pages/InboxPage';
import RoutinesPage from './pages/RoutinesPage';
import OrgChartPage from './pages/OrgChartPage';

function App() {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem('sidebarCollapsed') === 'true';
  });

  useEffect(() => {
    const handleSidebarToggle = (event: Event) => {
      const customEvent = event as CustomEvent<{ isCollapsed: boolean }>;
      setIsSidebarCollapsed(customEvent.detail?.isCollapsed ?? false);
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key === 'sidebarCollapsed') {
        setIsSidebarCollapsed(event.newValue === 'true');
      }
    };

    window.addEventListener('sidebarToggle', handleSidebarToggle as EventListener);
    window.addEventListener('storage', handleStorage);

    return () => {
      window.removeEventListener('sidebarToggle', handleSidebarToggle as EventListener);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  return (
    <div className="relative min-h-screen">
      <Sidebar />
      <div className={`pt-14 transition-all duration-300 md:pt-0 ${isSidebarCollapsed ? 'md:pl-[60px]' : 'md:pl-[240px]'}`}>
        <Routes>
          <Route path="/"                          element={<AgentsDashboard />} />
          <Route path="/dashboard"                 element={<Navigate to="/" replace />} />
          <Route path="/issues"                    element={<IssueDashboardPage />} />
          <Route path="/issues/:taskId"            element={<IssueDetailPage />} />
          <Route path="/routines"                  element={<RoutinesPage />} />
          <Route path="/routines/new"              element={<AgentSetupPage />} />
          <Route path="/routines/:agentId"         element={<AgentDetailPage />} />
          <Route path="/org"                       element={<OrgChartPage />} />
          <Route path="/research"                  element={<Navigate to="/" replace />} />
          <Route path="/earnings"                  element={<Navigate to="/" replace />} />
          <Route path="/chat"                      element={<Navigate to="/" replace />} />
          <Route path="/portfolio"                 element={<Portfolio />} />
          <Route path="/arena"                     element={<Navigate to="/" replace />} />
          <Route path="/memo"                      element={<Navigate to="/" replace />} />
          <Route path="/m/:slug"                   element={<Navigate to="/" replace />} />
          <Route path="/library"                   element={<Navigate to="/" replace />} />
          <Route path="/projects"                  element={<ProjectsListPage />} />
          <Route path="/projects/:projectId"       element={<ProjectWorkspace />} />
          <Route path="/cio"                       element={<Navigate to="/issues" replace />} />
          <Route path="/team"                      element={<Navigate to="/" replace />} />
          <Route path="/scheduled-agents"          element={<Navigate to="/routines" replace />} />
          <Route path="/scheduled-agents/new"      element={<Navigate to="/routines/new" replace />} />
          <Route path="/scheduled-agents/:agentId" element={<AgentDetailPage />} />
          <Route path="/inbox"                     element={<InboxPage />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
