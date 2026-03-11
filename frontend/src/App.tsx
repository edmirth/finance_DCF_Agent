import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import Portfolio from './pages/Portfolio';
import EarningsPage from './pages/EarningsPage';
import LibraryPage from './pages/LibraryPage';
import ProjectsListPage from './pages/ProjectsListPage';
import ProjectWorkspace from './pages/ProjectWorkspace';

function App() {
  return (
    <div className="relative min-h-screen">
      {/* Fixed Sidebar - overlays content */}
      <Sidebar />

      {/* Main Content Area */}
      <div>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/earnings" element={<EarningsPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/projects" element={<ProjectsListPage />} />
          <Route path="/projects/:projectId" element={<ProjectWorkspace />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
