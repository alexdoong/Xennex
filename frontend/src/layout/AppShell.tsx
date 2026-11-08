import { useState } from 'react';
import { X, Palette } from 'lucide-react';
import SkinEditorModal from '../features/skins/SkinEditorModal';
import SkinBackground from '../features/skins/SkinBackground';
import { cssImage } from '../utils/skinUtils';
import Titlebar from './Titlebar';
import CompactWorkspace from './CompactWorkspace';
import CloseConfirmModal from '../components/CloseConfirmModal';
import AppRoutes from '../AppRoutes';
import { APP_TABS, CUSTOMIZABLE_TABS, type AppTab } from './navigation';
import { useAppState } from '../hooks/useAppState';
import { useAutoHide } from '../hooks/useAutoHide';

export default function AppShell() {
  const [activeTab, setActiveTab] = useState<AppTab>('dashboard');
  const state = useAppState();
  const { sidebarMode, sidebarPosition, skinConfig, autoHideSidebar,
    autoHideTitlebar, closeToTray, setCloseToTray, showCloseConfirm,
    setShowCloseConfirm, api } = state;
  const { visible: showSidebar, onMouseEnter: handleSidebarMouseEnter,
    onMouseLeave: handleSidebarMouseLeave } = useAutoHide(autoHideSidebar);
  const { visible: showTitlebar, onMouseEnter: handleTitlebarMouseEnter,
    onMouseLeave: handleTitlebarMouseLeave } = useAutoHide(autoHideTitlebar);
  const handleResize = (dir: string) => window.chrome?.webview?.postMessage(`resizeWindow:${dir}`);

  const openFullWindow = (tab?: AppTab) => {
    if (tab) setActiveTab(tab);
    window.chrome?.webview?.postMessage('exitSidebar');
  };

  const effectiveCollapseEdge = state.effectiveCollapseEdge;
  const orderedTabs = [...CUSTOMIZABLE_TABS].sort((left, right) =>
    (skinConfig?.navigationOrder.indexOf(left.id) ?? 0) - (skinConfig?.navigationOrder.indexOf(right.id) ?? 0));
  const navigationTabs = [...orderedTabs, APP_TABS.find(tab => tab.id === 'settings')!];

  return (
    <div 
      className={`app-container ${sidebarMode ? 'sidebar-mode' : ''} pos-${sidebarPosition.toLowerCase()} collapse-${effectiveCollapseEdge.toLowerCase()} ${state.compactOpenHeight <= 560 ? 'compact-short' : ''} skin-nav-${skinConfig?.navigationPlacement || 'left'} skin-controls-${skinConfig?.controlsPlacement || 'right'} skin-frame-${skinConfig?.windowPresentation || 'floating'} skin-surface-${skinConfig?.surfaceStyle || 'glass'}`}
      id="app-container"
    >
      {!sidebarMode && (
        <>
          <div className="window-resize-edge edge-top" onMouseDown={() => handleResize('top')} />
          <div className="window-resize-edge edge-bottom" onMouseDown={() => handleResize('bottom')} />
          <div className="window-resize-edge edge-left" onMouseDown={() => handleResize('left')} />
          <div className="window-resize-edge edge-right" onMouseDown={() => handleResize('right')} />
          <div className="window-resize-corner corner-topleft" onMouseDown={() => handleResize('topleft')} />
          <div className="window-resize-corner corner-topright" onMouseDown={() => handleResize('topright')} />
          <div className="window-resize-corner corner-bottomleft" onMouseDown={() => handleResize('bottomleft')} />
          <div className="window-resize-corner corner-bottomright" onMouseDown={() => handleResize('bottomright')} />
        </>
      )}
      <div className="app-frame" id="app-frame">
        {/* Trigger Zone for Auto-Hide Sidebar */}
        {!sidebarMode && autoHideSidebar && !showSidebar && (
          <div 
            className="sidebar-trigger-zone"
            onMouseEnter={handleSidebarMouseEnter}
          />
        )}

        {/* Left Sidebar */}
        <div 
          className={`left-sidebar ${!showSidebar ? 'hidden' : ''}`}
          style={{ backgroundColor: skinConfig?.sidebarColor || undefined }}
          onMouseEnter={handleSidebarMouseEnter}
          onMouseLeave={handleSidebarMouseLeave}
        >
          {skinConfig?.sidebarImage && (
            <div 
              className="sidebar-bg-layer"
              style={{ backgroundImage: cssImage(skinConfig.sidebarImage), opacity: skinConfig.sidebarImageOpacity }}
            />
          )}

          <div className="sidebar-logo">
            <X size={32} color="var(--text-primary)" />
          </div>

          <div className="tabs">
            {navigationTabs.map(({ id, title, icon: Icon }) => (
              <button key={id} className={`tab-btn ${activeTab === id ? 'active' : ''}`}
                onClick={() => setActiveTab(id)} title={title}
                data-settings={id === 'settings' ? 'true' : undefined}>
                <Icon size={24} />
              </button>
            ))}
            <button className="tab-btn" title="Personalizar aparência" onClick={() => state.onEditSkin(state.activeSkinName)}><Palette size={24}/></button>
          </div>
        </div>

        {/* Main Window Container */}
        <div 
          className={`main-window ${!showSidebar || sidebarMode ? 'expanded' : ''}`}
          style={{ backgroundColor: skinConfig?.backgroundColor || '#0f131a' }}
        >
          <SkinBackground config={skinConfig}/>

          {/* Trigger Zone for Titlebar */}
          {!sidebarMode && autoHideTitlebar && !showTitlebar && (
            <div 
              className="titlebar-trigger-zone"
              onMouseEnter={handleTitlebarMouseEnter}
            />
          )}

          {/* Floating Titlebar */}
          <div 
            className={`floating-titlebar ${!showTitlebar ? 'hidden' : ''}`}
            style={{ backgroundColor: skinConfig?.titlebarColor || undefined }}
            onMouseEnter={handleTitlebarMouseEnter}
            onMouseLeave={handleTitlebarMouseLeave}
          >
            {skinConfig?.titlebarImage && (
              <div 
                className="titlebar-bg-layer"
                style={{ backgroundImage: cssImage(skinConfig.titlebarImage), opacity: skinConfig.titlebarImageOpacity }}
              />
            )}
            <Titlebar />
          </div>

          {sidebarMode && (
            <CompactWorkspace
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              openFullWindow={openFullWindow}
              {...state}
            />
          )}
          {sidebarMode && <div className="compact-edge-handle" aria-hidden="true"><span/></div>}
          <div className="content-wrapper" id="content">
            <AppRoutes activeTab={activeTab} {...state} />
          </div>

          {/* Window Resize Grip */}
          {!sidebarMode && (
            <div 
              className="window-resize-grip"
              title="Redimensionar janela"
              onMouseDown={(e) => {
                e.stopPropagation();
                handleResize('bottomright');
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M10 3L3 10M10 7L7 10M10 10.5H10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
          )}
        </div>

        {state.skinEditorName && <SkinEditorModal compact={sidebarMode} skinName={state.skinEditorName}
          onClose={() => state.setSkinEditorName(null)} onSaved={state.onSkinUpdated} onPreview={state.previewSkin}/>}
        {/* Modal de Confirmação ao Fechar */}
        <CloseConfirmModal 
          isOpen={showCloseConfirm}
          closeToTray={closeToTray}
          onToggleCloseToTray={(val) => {
            setCloseToTray(val);
            api?.SetCloseToTray(val);
          }}
          onClose={() => setShowCloseConfirm(false)}
          onMinimizeToTray={() => {
            setShowCloseConfirm(false);
            api?.MinimizeToTray();
          }}
          onExit={() => {
            setShowCloseConfirm(false);
            api?.Shutdown();
          }}
        />
      </div>
    </div>
  );
}
