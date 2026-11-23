import { createContext, useContext, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { BarChart3, ClipboardCheck, Search } from 'lucide-react';
import { api } from './api/client.js';
import logoMark from './assets/logo-mark-cream.png';
import SearchPage from './pages/SearchPage.jsx';
import EvaluatePage from './pages/EvaluatePage.jsx';
import MetricsPage from './pages/MetricsPage.jsx';

const InfoContext = createContext(null);
export const useInfo = () => useContext(InfoContext);

export default function App() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.info().then(setInfo, (e) => setError(e.message));
  }, []);

  return (
    <InfoContext.Provider value={info}>
      <div className="app">
        <header className="topbar">
          <div className="topbar-inner">
            <NavLink to="/" className="brand" aria-label="ThePremArchive, home">
              <img src={logoMark} alt="" className="brand-mark" width="70" height="40" />
              <span>
                <span className="brand-name">ThePremArchive</span>
                <span className="brand-tag">English Football Data</span>
              </span>
            </NavLink>
            <nav className="nav" aria-label="Sections">
              <NavLink to="/" end>
                <Search size={16} strokeWidth={2} aria-hidden /> Search
              </NavLink>
              <NavLink to="/evaluate">
                <ClipboardCheck size={16} strokeWidth={2} aria-hidden /> Rate results
              </NavLink>
              <NavLink to="/metrics">
                <BarChart3 size={16} strokeWidth={2} aria-hidden /> Metrics
              </NavLink>
            </nav>
            <div className="topbar-meta">
              {api.isMock && (
                <span className="pill pill-mock" title="Results come from project 2's saved runs; judgments are kept in this browser.">
                  Demo data
                </span>
              )}
            </div>
          </div>
        </header>

        {error ? (
          <div className="page">
            <div />
            <div className="message error">
              <h3>The search server is not answering.</h3>
              <p>{error} Check that it is running on port 8000, then reload this page.</p>
            </div>
          </div>
        ) : (
          <Routes>
            <Route path="/" element={<SearchPage />} />
            <Route path="/evaluate" element={<EvaluatePage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </div>
    </InfoContext.Provider>
  );
}
