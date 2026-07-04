import React from 'react';

interface DashboardTabProps {
  realStatus: boolean;
}

const DashboardTab: React.FC<DashboardTabProps> = ({ realStatus }) => {
  const api = window.chrome?.webview?.hostObjects?.api;

  return (
    <div className="tab-content" id="tab-osu">
      <h2>Wacom Drivers</h2>
      <div className="button-group">
        <button className="btn primary" onClick={() => api?.EnableWacom()}>
          Enable Wacom
        </button>
        <button className="btn danger" onClick={() => api?.DisableWacom()}>
          Disable Wacom
        </button>
      </div>

      <h2>REAL Engine</h2>
      <div className="status-indicator">
        <div className={`dot ${realStatus ? 'green' : 'red'}`}></div>
        <span>{realStatus ? 'Running' : 'Stopped'}</span>
      </div>
      <div className="button-group">
        <button className="btn primary" onClick={() => api?.StartReal()}>
          Start
        </button>
        <button className="btn danger" onClick={() => api?.StopReal()}>
          Stop
        </button>
      </div>
    </div>
  );
};

export default DashboardTab;
