import React, { useState, useEffect } from 'react';

const CloudTab: React.FC = () => {
  const [projectId, setProjectId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const api = window.chrome?.webview?.hostObjects?.api;

  useEffect(() => {
    const loadCreds = async () => {
      if (api) {
        const pid = await api.GetCloudProjectId();
        const ak = await api.GetCloudApiKey();
        if (pid) setProjectId(pid);
        if (ak) setApiKey(ak);
        if (pid && ak) {
          handleConnect(pid, ak);
        }
      }
    };
    loadCreds();
  }, []);

  const handleConnect = async (pid: string = projectId, ak: string = apiKey) => {
    setConnecting(true);
    if (api) {
      await api.SetCloudProjectId(pid);
      await api.SetCloudApiKey(ak);
    }
    
    // Simulate connection delay
    setTimeout(() => {
      setConnected(true);
      setConnecting(false);
    }, 800);
  };

  const handleDisconnect = () => {
    setConnected(false);
  };

  return (
    <div className="tab-content" id="tab-cloud">
      <h2>Cloud Sync</h2>
      <div className="card">
        <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
          Connect to Firebase / Firestore to backup and synchronize your settings and WuWa builds across devices.
        </p>
        <div className="input-group">
          <label>Project ID</label>
          <input
            type="text"
            className="modern-input"
            placeholder="e.g. my-project-123"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={connected || connecting}
          />
        </div>
        <div className="input-group">
          <label>API Key</label>
          <input
            type="password"
            className="modern-input"
            placeholder="AIzaSyB..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            disabled={connected || connecting}
          />
        </div>
      </div>

      <div className="status-indicator">
        <div className={`dot ${connected ? 'green' : ''}`}></div>
        <span>{connected ? 'Connected to Cloud' : 'Not Connected'}</span>
      </div>

      <div className="button-group">
        {!connected ? (
          <button
            className="btn primary"
            onClick={() => handleConnect()}
            disabled={connecting || !projectId || !apiKey}
          >
            {connecting ? 'Connecting...' : 'Connect'}
          </button>
        ) : (
          <button className="btn danger" onClick={handleDisconnect}>
            Disconnect
          </button>
        )}
      </div>
    </div>
  );
};

export default CloudTab;
