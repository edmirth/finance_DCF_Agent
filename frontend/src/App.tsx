import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import Portfolio from './pages/Portfolio';
import EarningsPage from './pages/EarningsPage';
import LibraryPage from './pages/LibraryPage';

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
        </Routes>
      </div>
    </div>
  );
}

export default App;
