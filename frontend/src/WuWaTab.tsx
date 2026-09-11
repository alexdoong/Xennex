import { useToast } from './components/ToastContainer';
import React from 'react';

const WuWaTab: React.FC = () => {
  const { showToast } = useToast();
  const handleScrape = () => {
    showToast("Sincronização de builds do Wuthering Waves em desenvolvimento.", "info");
  };

  return (
    <div className="tab-content" id="wuwa-tab">
      <div className="glass-panel">
        <h2 style={{ marginBottom: '16px' }}>Wuthering Waves Database</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
          Welcome to the WuWa database. Here you can fetch the latest builds and optimal echoes for your resonators.
        </p>

        <div className="glass-panel-inner" style={{ textAlign: 'center', padding: '48px' }}>
          <h3 style={{ fontSize: '18px', marginBottom: '16px' }}>Build Scraper (Coming Soon)</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', maxWidth: '400px', margin: '0 auto 24px' }}>
            Automatically scrape Prydwen or Akasha for optimal resonator builds and store them locally for offline reference.
          </p>
          <button className="btn primary btn-glow" onClick={handleScrape}>
            Sync WuWa Builds
          </button>
        </div>
      </div>
    </div>
  );
};

export default WuWaTab;
