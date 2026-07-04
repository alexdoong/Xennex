import React from 'react';

const Titlebar: React.FC = () => {
  const handleMinimize = () => {
    if (window.chrome?.webview) {
      window.chrome.webview.hostObjects.api.MinimizeToTray();
    }
  };

  const handleClose = () => {
    if (window.chrome?.webview) {
      window.chrome.webview.hostObjects.api.Shutdown();
    }
  };

  const handleMouseDown = () => {
    if (window.chrome?.webview) {
      window.chrome.webview.postMessage('dragWindow');
    }
  };

  return (
    <div className="titlebar" id="titlebar">
      <div className="drag-region" id="drag-region" onMouseDown={handleMouseDown}>
        Xennex
      </div>
      <div className="title-actions">
        <button onClick={handleMinimize} className="title-btn" aria-label="Minimize">
          —
        </button>
        <button onClick={handleClose} className="title-btn close" aria-label="Close">
          ✕
        </button>
      </div>
    </div>
  );
};

export default Titlebar;
