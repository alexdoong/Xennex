import React, { useState, useEffect } from 'react';
import type { SkinConfig } from './webview';
import SkinEditorModal from './SkinEditorModal';
import { Palette, Plus, FolderOpen, RotateCcw, X, Check, RefreshCw, Download, ExternalLink, ShieldCheck, Sparkles } from 'lucide-react';

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

  // Version & Updates State
  const [appVersion, setAppVersion] = useState('v0.2.0');
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'checking' | 'up-to-date' | 'available' | 'updating' | 'error'>('idle');
  const [updateData, setUpdateData] = useState<any>(null);
  const [updateMessage, setUpdateMessage] = useState('');

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
        if (api && api.GetAppVersion) {
          api.GetAppVersion().then((v: string) => setAppVersion(v || 'v0.2.0'));
        }
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

  
  const handleCheckUpdate = async () => {
    if (!api || !api.CheckForUpdates) return;
    setUpdateStatus('checking');
    setUpdateMessage('');
    try {
      const json = await api.CheckForUpdates();
      const res = JSON.parse(json);
      setUpdateData(res);
      if (!res.Success) {
        setUpdateStatus('error');
        setUpdateMessage(res.ErrorMessage || 'Erro ao consultar atualizações.');
      } else if (res.HasUpdate) {
        setUpdateStatus('available');
      } else {
        setUpdateStatus('up-to-date');
        setUpdateMessage(res.ErrorMessage || 'Você já está utilizando a versão mais recente.');
      }
    } catch (e: any) {
      setUpdateStatus('error');
      setUpdateMessage('Falha ao conectar com o GitHub.');
    }
  };

  const handleStartAutoUpdate = async () => {
    if (!api || !api.StartAutoUpdate || !updateData?.DownloadUrl) return;
    setUpdateStatus('updating');
    setUpdateMessage('Baixando e instalando nova versão... O app será reiniciado em instantes.');
    try {
      const ok = await api.StartAutoUpdate(updateData.DownloadUrl);
      if (!ok) {
        setUpdateStatus('error');
        setUpdateMessage('Falha ao baixar atualização. Você pode baixar manualmente pelo GitHub.');
      }
    } catch (e) {
      setUpdateStatus('error');
      setUpdateMessage('Erro ao aplicar atualização automática.');
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


        {/* Version & Updates Card */}
        <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{
                width: '40px', height: '40px', borderRadius: '12px',
                background: 'rgba(255, 255, 255, 0.06)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: '1px solid rgba(255, 255, 255, 0.1)'
              }}>
                <Sparkles size={20} color="var(--primary)" />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h3 style={{ margin: 0, fontSize: '16px' }}>Sobre o Xennex</h3>
                  <span style={{
                    padding: '2px 8px', borderRadius: '6px',
                    fontSize: '12px', fontWeight: 600,
                    background: 'rgba(139, 92, 246, 0.2)', color: 'var(--primary)',
                    border: '1px solid rgba(139, 92, 246, 0.3)'
                  }}>
                    {appVersion}
                  </span>
                </div>
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  HUD & Gaming Companion por Alex Doong
                </span>
              </div>
            </div>

            <button
              className="btn"
              onClick={handleCheckUpdate}
              disabled={updateStatus === 'checking' || updateStatus === 'updating'}
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <RefreshCw size={16} className={updateStatus === 'checking' ? 'spin' : ''} />
              {updateStatus === 'checking' ? 'Verificando...' : 'Verificar Atualizações'}
            </button>
          </div>

          {/* Update Status Feedback */}
          {updateStatus === 'up-to-date' && (
            <div style={{
              padding: '12px 16px', borderRadius: '10px',
              background: 'rgba(34, 197, 94, 0.1)',
              border: '1px solid rgba(34, 197, 94, 0.3)',
              display: 'flex', alignItems: 'center', gap: '10px',
              color: 'hsl(142, 70%, 65%)', fontSize: '13px'
            }}>
              <ShieldCheck size={18} />
              <span>{updateMessage}</span>
            </div>
          )}

          {updateStatus === 'error' && (
            <div style={{
              padding: '12px 16px', borderRadius: '10px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              color: 'hsl(0, 80%, 75%)', fontSize: '13px'
            }}>
              <span>{updateMessage}</span>
              <button
                className="btn"
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => api?.OpenBrowser('https://github.com/alexdoong/Xennex/releases')}
              >
                Abrir GitHub
              </button>
            </div>
          )}

          {updateStatus === 'updating' && (
            <div style={{
              padding: '14px 16px', borderRadius: '10px',
              background: 'rgba(139, 92, 246, 0.15)',
              border: '1px solid var(--primary)',
              display: 'flex', alignItems: 'center', gap: '12px',
              fontSize: '13px'
            }}>
              <RefreshCw size={18} className="spin" color="var(--primary)" />
              <span>{updateMessage}</span>
            </div>
          )}

          {updateStatus === 'available' && updateData && (
            <div style={{
              padding: '16px', borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(59, 130, 246, 0.1))',
              border: '1px solid var(--primary)',
              display: 'flex', flexDirection: 'column', gap: '12px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '15px', fontWeight: 600 }}>Nova versão disponível:</span>
                  <span style={{
                    padding: '2px 8px', borderRadius: '6px',
                    fontSize: '13px', fontWeight: 700,
                    background: 'var(--primary)', color: '#fff'
                  }}>
                    {updateData.LatestVersion}
                  </span>
                </div>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {updateData.ReleaseTitle}
                </span>
              </div>

              {updateData.ReleaseNotes && (
                <div style={{
                  padding: '10px 12px', borderRadius: '8px',
                  background: 'rgba(0, 0, 0, 0.3)',
                  fontSize: '12px', color: 'var(--text-secondary)',
                  maxHeight: '100px', overflowY: 'auto', whiteSpace: 'pre-wrap'
                }}>
                  {updateData.ReleaseNotes}
                </div>
              )}

              <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
                {updateData.DownloadUrl && (
                  <button
                    className="btn primary"
                    onClick={handleStartAutoUpdate}
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600 }}
                  >
                    <Download size={16} />
                    Atualizar Agora Automaticamente
                  </button>
                )}

                <button
                  className="btn"
                  onClick={() => api?.OpenBrowser(updateData.HtmlUrl || 'https://github.com/alexdoong/Xennex/releases')}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                >
                  <ExternalLink size={16} />
                  Ver no GitHub
                </button>
              </div>
            </div>
          )}
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
