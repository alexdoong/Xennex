import React, { useState, useEffect } from 'react';
import Titlebar from './Titlebar';
import DashboardTab from './DashboardTab';
import WuWaTab from './WuWaTab';
import CloudTab from './CloudTab';
import SettingsTab from './SettingsTab';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'osu' | 'wuwa-db' | 'cloud' | 'settings'>('osu');
  const [realStatus, setRealStatus] = useState(false);
  const [sidebarMode, setSidebarMode] = useState(false);

  useEffect(() => {
    // Setup C# to JS callbacks
    window.updateRealStatus = (isRunning: boolean) => {
      setRealStatus(isRunning);
    };

    window.updateSidebarMode = (isSidebar: boolean) => {
      setSidebarMode(isSidebar);
    };

    return () => {
      // @ts-ignore
      delete window.updateRealStatus;
      // @ts-ignore
      delete window.updateSidebarMode;
    };
  }, []);

  return (
    <div className={`app-container ${sidebarMode ? 'sidebar-mode' : ''}`} id="app-container">
      {!sidebarMode && <Titlebar />}

      <div className="content-wrapper" id="content">
        <div className="tabs">
          <button
            className={`tab-btn ${activeTab === 'osu' ? 'active' : ''}`}
            onClick={() => setActiveTab('osu')}
          >
            Dashboard
          </button>
          <button
            className={`tab-btn ${activeTab === 'wuwa-db' ? 'active' : ''}`}
            onClick={() => setActiveTab('wuwa-db')}
          >
            WuWa Database
          </button>
          <button
            className={`tab-btn ${activeTab === 'cloud' ? 'active' : ''}`}
            onClick={() => setActiveTab('cloud')}
          >
            Cloud
          </button>
          <button
            className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            Config
          </button>
        </div>

        {activeTab === 'osu' && <DashboardTab realStatus={realStatus} />}
        {activeTab === 'wuwa-db' && <WuWaTab />}
        {activeTab === 'cloud' && <CloudTab />}
        {activeTab === 'settings' && <SettingsTab sidebarMode={sidebarMode} setSidebarMode={setSidebarMode} />}
      </div>

      {sidebarMode && (
        <div 
          id="pull-tab" 
          className="pull-tab"
          onMouseDown={() => {
            if (window.chrome?.webview) {
              window.chrome.webview.postMessage('dragWindow');
            }
          }}
        >
          <div className="pull-tab-line"></div>
          <div className="pull-tab-line"></div>
        </div>
      )}
    </div>
  );
};

export default App;
