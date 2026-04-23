import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import Portfolio from './pages/Portfolio';
import EarningsPage from './pages/EarningsPage';
import ArenaPage from './pages/ArenaPage';
import InvestmentMemoPage from './pages/InvestmentMemoPage';
import MemoSharePage from './pages/MemoSharePage';
import LibraryPage from './pages/LibraryPage';
import ProjectsListPage from './pages/ProjectsListPage';
import ProjectWorkspace from './pages/ProjectWorkspace';
import AgentsDashboard from './pages/AgentsDashboard';
import AgentSetupPage from './pages/AgentSetupPage';
import AgentDetailPage from './pages/AgentDetailPage';
import InboxPage from './pages/InboxPage';

function App() {
  return (
    <div className="relative min-h-screen">
      {/* Fixed Sidebar - overlays content */}
      <Sidebar />

      {/* Main Content Area - offset for mobile header and desktop sidebar */}
      <div className="pt-14 md:pt-0 md:pl-[60px] lg:pl-[240px] transition-all duration-300">
        <Routes>
          <Route path="/" element={<InvestmentMemoPage />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/earnings" element={<EarningsPage />} />
          <Route path="/arena" element={<ArenaPage />} />
          <Route path="/chat" element={<ChatPage />} />
          {/* /memo kept as alias so existing links don't break */}
          <Route path="/memo" element={<InvestmentMemoPage />} />
          <Route path="/m/:slug" element={<MemoSharePage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/projects" element={<ProjectsListPage />} />
          <Route path="/projects/:projectId" element={<ProjectWorkspace />} />
          <Route path="/scheduled-agents" element={<AgentsDashboard />} />
          <Route path="/scheduled-agents/new" element={<AgentSetupPage />} />
          <Route path="/scheduled-agents/:agentId" element={<AgentDetailPage />} />
          <Route path="/inbox" element={<InboxPage />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
