import React, { useState, useEffect } from 'react';

const CloudTab: React.FC = () => {
  const [projectId, setProjectId] = useState('');
  const [apiKey, setApiKey] = useState('');

  const api = window.chrome?.webview?.hostObjects?.api;

  useEffect(() => {
    const loadCloud = async () => {
      if (api) {
        setProjectId(await api.GetCloudProjectId());
        setApiKey(await api.GetCloudApiKey());
      }
    };
    loadCloud();
  }, []);

  const handleSave = () => {
    if (api) {
      api.SetCloudProjectId(projectId);
      api.SetCloudApiKey(apiKey);
      alert("Cloud Config Saved!");
    }
  };

  return (
    <div className="tab-content" id="cloud-tab">
      <div className="glass-panel">
        <h2 style={{ marginBottom: '16px' }}>Xennex Cloud Link</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
          Connect your custom BYOD (Bring Your Own Database) to sync settings across machines.
        </p>

        <div className="glass-panel-inner" style={{ maxWidth: '400px' }}>
          <div className="input-group">
            <label>Project ID (e.g. Firebase or Supabase ID)</label>
            <input 
              type="text" 
              className="modern-input" 
              value={projectId} 
              onChange={e => setProjectId(e.target.value)}
              placeholder="my-cool-project-123"
            />
          </div>
          
          <div className="input-group" style={{ marginBottom: '24px' }}>
            <label>API Key (Keep this secret!)</label>
            <input 
              type="password" 
              className="modern-input" 
              value={apiKey} 
              onChange={e => setApiKey(e.target.value)}
              placeholder="AIzaSyB..."
            />
          </div>

          <button className="btn primary btn-glow" onClick={handleSave}>
            Save Connection
          </button>
        </div>
      </div>
    </div>
  );
};

export default CloudTab;
