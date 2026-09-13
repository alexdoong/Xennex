import React from 'react';
import { Minus, X } from 'lucide-react';

const Titlebar: React.FC = () => {
  const handleMinimize = () => {
    if (window.chrome?.webview) {
      window.chrome.webview.hostObjects.api.MinimizeToTray();
    }
  };

  const handleClose = () => {
    if (window.showCloseModal) {
      window.showCloseModal();
    } else if (window.chrome?.webview) {
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
      <div className="drag-region" id="drag-region" onMouseDown={handleMouseDown} title="Drag window">
        ✕
      </div>
      <div className="title-actions">
        <button onClick={handleMinimize} className="title-btn" aria-label="Minimize">
          <Minus size={14} />
        </button>
        <button onClick={handleClose} className="title-btn close" aria-label="Close">
          <X size={14} />
        </button>
      </div>
    </div>
  );
};

export default Titlebar;
