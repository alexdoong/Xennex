import React, { useState, useEffect } from 'react';
import type { SkinConfig } from './webview';
import SkinEditorModal from './SkinEditorModal';
import { Palette, Plus, FolderOpen, RotateCcw, X, Check } from 'lucide-react';

interface SettingsTabProps {
  sidebarMode: boolean;
  autoHideSidebar: boolean;
  setAutoHideSidebar: (val: boolean) => void;
  autoHideTitlebar: boolean;
  setAutoHideTitlebar: (val: boolean) => void;
  closeToTray: boolean;
  setCloseToTray: (val: boolean) => void;
  onSkinUpdated?: (config: SkinConfig) => void;
}

const SettingsTab: React.FC<SettingsTabProps> = ({ 
  sidebarMode, 
  autoHideSidebar,
  setAutoHideSidebar,
  autoHideTitlebar,
  setAutoHideTitlebar,
  closeToTray,
  setCloseToTray,
  onSkinUpdated
}) => {
  const [sidebarPosition, setSidebarPosition] = useState('MiddleRight');
  const [availableSkins, setAvailableSkins] = useState<string[]>([]);
  const [activeSkin, setActiveSkin] = useState<string>('default');

  // Skin Editor & Creation Modals
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [isNewSkinModalOpen, setIsNewSkinModalOpen] = useState(false);
  const [newSkinNameInput, setNewSkinNameInput] = useState('');
  const [skinErrorMsg, setSkinErrorMsg] = useState('');

  const api = window.chrome?.webview?.hostObjects?.api;

  useEffect(() => {
    const loadSettings = async () => {
      if (api) {
        // closeToTray passed as prop
        setSidebarPosition(await api.GetSidebarPosition());
        const skins = await api.GetAvailableSkins();
        setAvailableSkins(skins);
        const currentActive = await api.GetActiveSkin();
        setActiveSkin(currentActive || 'default');
      }
    };
    loadSettings();
  }, []);

  const handleCloseToTray = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setCloseToTray(val);
    api?.SetCloseToTray(val);
  };

  const handleAutoHideSidebar = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setAutoHideSidebar(val);
    api?.SetAutoHideSidebar(val);
  };

  const handleAutoHideTitlebar = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setAutoHideTitlebar(val);
    api?.SetAutoHideTitlebar(val);
  };

  const handleSkinChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setActiveSkin(val);
    if (api) {
      await api.SetActiveSkin(val);
      const json = await api.GetSkinConfig(val);
      if (json && onSkinUpdated) {
        try {
          const parsed = JSON.parse(json);
          onSkinUpdated(parsed);
        } catch (err) {
          console.error('Failed to parse skin config:', err);
        }
      }
    }
  };

  const handleOpenSkinFolder = () => {
    api?.OpenSkinFolder();
  };

  const handleReloadSkin = async () => {
    if (api && onSkinUpdated) {
      const json = await api.GetSkinConfig(activeSkin);
      if (json) {
        try {
          const parsed = JSON.parse(json);
          onSkinUpdated(parsed);
        } catch (err) {
          console.error('Reload skin error:', err);
        }
      }
    }
  };

  const handleCreateNewSkin = async () => {
    const trimmed = newSkinNameInput.trim();
    if (!trimmed) {
      setSkinErrorMsg('Por favor, informe um nome para a skin.');
      return;
    }

    if (!api) return;

    try {
      const success = await api.CreateNewSkin(trimmed, activeSkin);
      if (success) {
        const skins = await api.GetAvailableSkins();
        setAvailableSkins(skins);
        setActiveSkin(trimmed);
        setIsNewSkinModalOpen(false);
        setNewSkinNameInput('');
        setSkinErrorMsg('');
        // Open the editor immediately for the new skin
        setIsEditorOpen(true);
      } else {
        setSkinErrorMsg('Não foi possível criar a skin. Verifique o nome informado.');
      }
    } catch (err) {
      console.error('Create skin error:', err);
      setSkinErrorMsg('Erro ao criar skin.');
    }
  };

  const handleSidebarPosition = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSidebarPosition(val);
    api?.SetSidebarPosition(val);
    
    if (window.updateSidebarPosition) {
        window.updateSidebarPosition(val);
    }
  };

  const toggleSidebarMode = () => {
    if (api) {
      api.ToggleSidebar();
    } else if (window.chrome?.webview) {
      window.chrome.webview.postMessage(sidebarMode ? 'exitSidebar' : 'enterSidebar');
    }
  };

  return (
    <div className="tab-content" id="settings-tab">
      <div className="glass-panel">
        <h2 style={{ marginBottom: '24px' }}>System Settings</h2>
        
        <div className="glass-panel-inner">
          <h3 style={{ fontSize: '16px', marginBottom: '16px', color: 'var(--primary)' }}>Application Behavior</h3>
          
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div>
              <span style={{ display: 'block', fontSize: '14px', fontWeight: 500 }}>Close to System Tray</span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>App stays running in background when closed</span>
            </div>
            <label className="switch">
              <input type="checkbox" checked={closeToTray} onChange={handleCloseToTray} />
              <span className="slider"></span>
            </label>
          </div>
        </div>

        <div className="glass-panel-inner">
          <h3 style={{ fontSize: '16px', marginBottom: '16px', color: 'var(--primary)' }}>UI & Layout</h3>
          
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div>
              <span style={{ display: 'block', fontSize: '14px', fontWeight: 500 }}>Auto-Hide Sidebar</span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Hover left edge to reveal the navigation sidebar</span>
            </div>
            <label className="switch">
              <input type="checkbox" checked={autoHideSidebar} onChange={handleAutoHideSidebar} />
              <span className="slider"></span>
            </label>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div>
              <span style={{ display: 'block', fontSize: '14px', fontWeight: 500 }}>Auto-Hide Titlebar</span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Hover top edge to reveal window controls</span>
            </div>
            <label className="switch">
              <input type="checkbox" checked={autoHideTitlebar} onChange={handleAutoHideTitlebar} />
              <span className="slider"></span>
            </label>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
            <div>
              <span style={{ display: 'block', fontSize: '14px', fontWeight: 500 }}>Compact Mode (Widget)</span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Shrink app to a side widget that auto-hides off-screen</span>
            </div>
            <button className="btn primary" onClick={toggleSidebarMode}>
              {sidebarMode ? 'Exit Compact Mode' : 'Enter Compact Mode'}
            </button>
          </div>
          
          {sidebarMode && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div>
                  <span style={{ display: 'block', fontSize: '14px', fontWeight: 500 }}>Widget Position</span>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Screen edge for compact mode</span>
                </div>
                <select className="modern-input" style={{ width: '150px' }} value={sidebarPosition} onChange={handleSidebarPosition}>
                  <option value="MiddleRight">Meio Direito (Middle Right)</option>
                  <option value="TopLeft">Topo Esquerdo (Top Left)</option>
                  <option value="MiddleLeft">Meio Esquerdo (Middle Left)</option>
                </select>
              </div>
            </>
          )}
        </div>

        {/* Skin Engine Section */}
        <div className="glass-panel-inner" style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '16px', marginBottom: '16px', color: 'var(--primary)' }}>Skin Engine & Customização</h3>
          
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
            <div>
              <span style={{ display: 'block', fontSize: '14px', fontWeight: 500 }}>Skin Ativa</span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Escolha o tema e estilo visual da interface</span>
            </div>
            <select className="modern-input" style={{ width: '180px' }} value={activeSkin} onChange={handleSkinChange}>
              {availableSkins.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
            <button 
              className="btn primary" 
              onClick={() => setIsEditorOpen(true)}
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <Palette size={16} />
              Editar Skin no App
            </button>

            <button 
              className="btn" 
              onClick={() => {
                setNewSkinNameInput('');
                setSkinErrorMsg('');
                setIsNewSkinModalOpen(true);
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <Plus size={16} />
              Nova Skin
            </button>

            <button 
              className="btn" 
              onClick={handleOpenSkinFolder}
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <FolderOpen size={16} />
              Abrir Pasta
            </button>

            <button 
              className="btn" 
              onClick={handleReloadSkin}
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <RotateCcw size={16} />
              Recarregar
            </button>
          </div>
        </div>

      </div>

      {/* Skin Editor Visual Modal */}
      {isEditorOpen && (
        <SkinEditorModal
          skinName={activeSkin}
          isOpen={isEditorOpen}
          onClose={() => setIsEditorOpen(false)}
          onSaved={(updatedConfig) => {
            if (onSkinUpdated) {
              onSkinUpdated(updatedConfig);
            }
          }}
        />
      )}

      {/* New Skin Dialog Modal */}
      {isNewSkinModalOpen && (
        <div className="modal-backdrop">
          <div className="glass-panel" style={{ width: '420px', padding: '24px', position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Plus size={18} color="var(--primary)" />
                Criar Nova Skin
              </h3>
              <button className="btn icon-only" onClick={() => setIsNewSkinModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              Uma nova pasta será criada duplicando a configuração da skin atual ({activeSkin}).
            </p>

            <div style={{ marginBottom: '16px' }}>
              <label className="skin-label" style={{ display: 'block', marginBottom: '6px' }}>Nome da Skin</label>
              <input
                type="text"
                className="modern-input"
                placeholder="Ex: Cyberpunk, DarkRed, Minimal..."
                value={newSkinNameInput}
                onChange={e => setNewSkinNameInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleCreateNewSkin(); }}
                autoFocus
                style={{ width: '100%' }}
              />
            </div>

            {skinErrorMsg && (
              <div style={{ color: 'var(--danger)', fontSize: '12px', marginBottom: '12px' }}>
                {skinErrorMsg}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button className="btn" onClick={() => setIsNewSkinModalOpen(false)}>
                Cancelar
              </button>
              <button className="btn primary" onClick={handleCreateNewSkin} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Check size={16} />
                Criar e Editar
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default SettingsTab;
