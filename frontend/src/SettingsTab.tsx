import React, { useState, useEffect } from 'react';

interface SettingsTabProps {
  sidebarMode: boolean;
  setSidebarMode: (mode: boolean) => void;
}

const SettingsTab: React.FC<SettingsTabProps> = ({ sidebarMode, setSidebarMode }) => {
  const [closeToTray, setCloseToTray] = useState(false);
  const [hidePullTab, setHidePullTab] = useState(false);

  const api = window.chrome?.webview?.hostObjects?.api;

  useEffect(() => {
    const loadSettings = async () => {
      if (api) {
        setCloseToTray(await api.GetCloseToTray());
        setHidePullTab(await api.GetHideSidebarPullTab());
      }
    };
    loadSettings();
  }, []);

  const handleCloseToTray = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setCloseToTray(val);
    api?.SetCloseToTray(val);
  };

  const handleHidePullTab = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setHidePullTab(val);
    api?.SetHideSidebarPullTab(val);
  };

  const handleSidebarToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSidebarMode(e.target.checked);
    api?.ToggleSidebar();
  };

  return (
    <div className="tab-content" id="tab-settings">
      <h2>Settings</h2>
      
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div className="setting-item">
          <span>Close to Tray</span>
          <label className="switch">
            <input type="checkbox" checked={closeToTray} onChange={handleCloseToTray} />
            <span className="slider"></span>
          </label>
        </div>

        <div className="setting-item">
          <span>Hide Pull Tab</span>
          <label className="switch">
            <input type="checkbox" checked={hidePullTab} onChange={handleHidePullTab} />
            <span className="slider"></span>
          </label>
        </div>

        <div className="setting-item" style={{ borderBottom: 'none' }}>
          <span>Sidebar Mode</span>
          <label className="switch">
            <input type="checkbox" checked={sidebarMode} onChange={handleSidebarToggle} />
            <span className="slider"></span>
          </label>
        </div>
      </div>
    </div>
  );
};

export default SettingsTab;
