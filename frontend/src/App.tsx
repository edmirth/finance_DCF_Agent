import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Portfolio from './pages/Portfolio';
import EarningsPage from './pages/EarningsPage';
import InvestmentMemoPage from './pages/InvestmentMemoPage';
import MemoSharePage from './pages/MemoSharePage';
import LibraryPage from './pages/LibraryPage';
import ProjectsListPage from './pages/ProjectsListPage';
import ProjectWorkspace from './pages/ProjectWorkspace';
import IssueDashboardPage from './pages/IssueDashboardPage';
import IssueDetailPage from './pages/IssueDetailPage';
import AgentsDashboard from './pages/AgentsDashboard';
import AgentSetupPage from './pages/AgentSetupPage';
import AgentDetailPage from './pages/AgentDetailPage';
import InboxPage from './pages/InboxPage';
import ResearchWorkstation from './pages/ResearchWorkstation';
import CioPage from './pages/CioPage';

function App() {
  return (
    <div className="relative min-h-screen">
      <Sidebar />
      <div className="pt-14 md:pt-0 md:pl-[60px] lg:pl-[240px] transition-all duration-300">
        <Routes>
          <Route path="/"                          element={<IssueDashboardPage />} />
          <Route path="/dashboard"                 element={<Navigate to="/" replace />} />
          <Route path="/issues/:taskId"            element={<IssueDetailPage />} />
          <Route path="/research"                  element={<ResearchWorkstation />} />
          <Route path="/earnings"                  element={<EarningsPage />} />
          <Route path="/chat"                      element={<Navigate to="/" replace />} />
          <Route path="/portfolio"                 element={<Portfolio />} />
          <Route path="/arena"                     element={<Navigate to="/memo" replace />} />
          <Route path="/memo"                      element={<InvestmentMemoPage />} />
          <Route path="/m/:slug"                   element={<MemoSharePage />} />
          <Route path="/library"                   element={<LibraryPage />} />
          <Route path="/projects"                  element={<ProjectsListPage />} />
          <Route path="/projects/:projectId"       element={<ProjectWorkspace />} />
          <Route path="/cio"                       element={<CioPage />} />
          <Route path="/team"                      element={<AgentsDashboard />} />
          <Route path="/scheduled-agents"          element={<Navigate to="/cio" replace />} />
          <Route path="/scheduled-agents/new"      element={<AgentSetupPage />} />
          <Route path="/scheduled-agents/:agentId" element={<AgentDetailPage />} />
          <Route path="/inbox"                     element={<InboxPage />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
