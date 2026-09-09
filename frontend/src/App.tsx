import React, { useState, useEffect, useCallback, useRef } from 'react';
import Titlebar from './Titlebar';
import DashboardTab from './DashboardTab';
import WuWaTab from './WuWaTab';
import CloudTab from './CloudTab';
import SettingsTab from './SettingsTab';
import HandMotionTab from './HandMotionTab';
import StreamTab from './StreamTab';
import StreamViewer from './StreamViewer';
import CloseConfirmModal from './CloseConfirmModal';
import { computeBorder, normalizeSkinConfig } from './utils/skinUtils';
import type { SkinConfig } from './webview';
import { LayoutDashboard, Database, Cloud, Hand, Settings, X, Tv } from 'lucide-react';

const App: React.FC = () => {
  const isViewerMode = new URLSearchParams(window.location.search).get('mode') === 'viewer';
  if (isViewerMode) {
    return <StreamViewer />;
  }

  const [activeTab, setActiveTab] = useState<'osu' | 'wuwa-db' | 'cloud' | 'settings' | 'hand-motion' | 'stream'>('osu');
  const [realStatus, setRealStatus] = useState(false);
  const [handMotionStatus, setHandMotionStatus] = useState(false);
  const [sidebarMode, setSidebarMode] = useState(false);
  const [sidebarPosition, setSidebarPosition] = useState('MiddleRight');

  // Skin Configuration State
  const [skinConfig, setSkinConfig] = useState<SkinConfig | null>(null);

  // Auto-hide States
  const [isSidebarHovered, setIsSidebarHovered] = useState(false);
  const [isTitlebarHovered, setIsTitlebarHovered] = useState(false);
  const [autoHideSidebar, setAutoHideSidebar] = useState(true);
  const [autoHideTitlebar, setAutoHideTitlebar] = useState(true);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

    const sidebarLeaveTimerRef = useRef<number | null>(null);
  const titlebarLeaveTimerRef = useRef<number | null>(null);
  const api = window.chrome?.webview?.hostObjects?.api;

  const applySkin = useCallback((cfg: SkinConfig) => {
    if (!cfg) return;
    const root = document.documentElement;
    if (cfg.primaryColor) {
      root.style.setProperty('--primary', cfg.primaryColor);
      const glow = cfg.primaryColor.startsWith('hsl') 
        ? cfg.primaryColor.replace('hsl', 'hsla').replace(')', ', 0.4)')
        : cfg.primaryColor;
      root.style.setProperty('--primary-glow', glow);
    }
    if (cfg.primaryHover) {
      root.style.setProperty('--primary-hover', cfg.primaryHover);
    } else if (cfg.primaryColor) {
      root.style.setProperty('--primary-hover', cfg.primaryColor);
    }
    if (cfg.textColor) {
      root.style.setProperty('--text-primary', cfg.textColor);
    }

    const b = computeBorder(cfg.borderColor, cfg.borderOpacity, cfg.borderWidth);
    root.style.setProperty('--border-color', b.color);
    root.style.setProperty('--border-width', b.width);
    root.style.setProperty('--border', b.border);
  }, []);

  useEffect(() => {
    window.updateRealStatus = (isRunning: boolean) => setRealStatus(isRunning);
    window.updateHandMotionStatus = (isRunning: boolean) => setHandMotionStatus(isRunning);
    window.updateSidebarMode = (isSidebar: boolean) => setSidebarMode(isSidebar);
    window.updateSidebarPosition = (pos: string) => setSidebarPosition(pos);
    window.showCloseModal = () => setShowCloseConfirm(true);

    if (api) {
      api.GetSidebarPosition().then(pos => setSidebarPosition(pos || 'MiddleRight'));
      api.GetAutoHideSidebar().then(val => setAutoHideSidebar(val));
      api.GetAutoHideTitlebar().then(val => setAutoHideTitlebar(val));
      api.IsSidebarMode().then(val => setSidebarMode(val));

      api.GetActiveSkin().then(async active => {
        const json = await api.GetSkinConfig(active || 'default');
        if (json && json.trim() !== '{}' && json.trim() !== '') {
          try {
            const rawParsed = JSON.parse(json);
            const parsed = normalizeSkinConfig(rawParsed);
            setSkinConfig(parsed);
            applySkin(parsed);
          } catch (e) {
            console.error('Error parsing active skin config:', e);
          }
        }
      });
    }

    return () => {
      // @ts-ignore
      delete window.updateRealStatus;
      // @ts-ignore
      delete window.updateHandMotionStatus;
      // @ts-ignore
      delete window.updateSidebarMode;
      // @ts-ignore
      delete window.updateSidebarPosition;
      // @ts-ignore
      delete window.showCloseModal;
    };
  }, [api, applySkin]);

  const handleSidebarMouseEnter = () => {
    if (sidebarLeaveTimerRef.current) {
      window.clearTimeout(sidebarLeaveTimerRef.current);
      sidebarLeaveTimerRef.current = null;
    }
    setIsSidebarHovered(true);
  };

  const handleSidebarMouseLeave = () => {
    if (sidebarLeaveTimerRef.current) {
      window.clearTimeout(sidebarLeaveTimerRef.current);
    }
    sidebarLeaveTimerRef.current = window.setTimeout(() => {
      setIsSidebarHovered(false);
    }, 500);
  };

  const handleTitlebarMouseEnter = () => {
    if (titlebarLeaveTimerRef.current) {
      window.clearTimeout(titlebarLeaveTimerRef.current);
      titlebarLeaveTimerRef.current = null;
    }
    setIsTitlebarHovered(true);
  };

  const handleTitlebarMouseLeave = () => {
    if (titlebarLeaveTimerRef.current) {
      window.clearTimeout(titlebarLeaveTimerRef.current);
    }
    titlebarLeaveTimerRef.current = window.setTimeout(() => {
      setIsTitlebarHovered(false);
    }, 500);
  };

  const showSidebar = !autoHideSidebar || isSidebarHovered;
  const showTitlebar = !autoHideTitlebar || isTitlebarHovered;

  return (
    <div 
      className={`app-container ${sidebarMode ? 'sidebar-mode' : ''} pos-${sidebarPosition.toLowerCase()}`} 
      id="app-container"
    >
      <div className="app-frame" id="app-frame">
        {/* Trigger Zone for Auto-Hide Sidebar */}
        {autoHideSidebar && !showSidebar && (
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
              style={{ backgroundImage: `url('${skinConfig.sidebarImage}')` }}
            />
          )}

          <div className="sidebar-logo">
            <X size={32} color="var(--text-primary)" />
          </div>

          <div className="tabs">
            <button
              className={`tab-btn ${activeTab === 'osu' ? 'active' : ''}`}
              onClick={() => setActiveTab('osu')}
              title="Dashboard"
            >
              <LayoutDashboard size={24} />
            </button>
            <button
              className={`tab-btn ${activeTab === 'wuwa-db' ? 'active' : ''}`}
              onClick={() => setActiveTab('wuwa-db')}
              title="WuWa Database"
            >
              <Database size={24} />
            </button>
            <button
              className={`tab-btn ${activeTab === 'cloud' ? 'active' : ''}`}
              onClick={() => setActiveTab('cloud')}
              title="Cloud"
            >
              <Cloud size={24} />
            </button>
            <button
              className={`tab-btn ${activeTab === 'stream' ? 'active' : ''}`}
              onClick={() => setActiveTab('stream')}
              title="Compartilhamento de Tela & Streams"
            >
              <Tv size={24} />
            </button>
            <button
              className={`tab-btn ${activeTab === 'hand-motion' ? 'active' : ''}`}
              onClick={() => setActiveTab('hand-motion')}
              title="Hand Motion"
            >
              <Hand size={24} />
            </button>
            <button
              className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
              onClick={() => setActiveTab('settings')}
              title="Config"
              style={{ marginTop: 'auto' }}
            >
              <Settings size={24} />
            </button>
          </div>
        </div>

        {/* Main Window Container */}
        <div 
          className={`main-window ${!showSidebar || sidebarMode ? 'expanded' : ''}`}
          style={{ backgroundColor: skinConfig?.backgroundColor || '#0f131a' }}
        >
          {skinConfig?.backgroundType === 'video' && skinConfig.backgroundUrl ? (
            <video
              key={skinConfig.backgroundUrl}
              className="main-window-bg-video"
              src={skinConfig.backgroundUrl}
              autoPlay
              loop
              muted
              playsInline
              style={{
                opacity: skinConfig?.backgroundOpacity ?? 1,
                filter: skinConfig?.backgroundBlur ? `blur(${skinConfig.backgroundBlur}px)` : 'none'
              }}
            />
          ) : (
            <div
              className="main-window-bg-image"
              style={{
                backgroundImage: skinConfig?.backgroundUrl ? `url('${skinConfig.backgroundUrl}')` : undefined,
                opacity: skinConfig?.backgroundOpacity ?? 1,
                filter: skinConfig?.backgroundBlur ? `blur(${skinConfig.backgroundBlur}px)` : 'none'
              }}
            />
          )}

          {/* Trigger Zone for Titlebar */}
          {autoHideTitlebar && !showTitlebar && (
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
                style={{ backgroundImage: `url('${skinConfig.titlebarImage}')` }}
              />
            )}
            <Titlebar />
          </div>

          <div className="content-wrapper" id="content">
            {activeTab === 'osu' && <DashboardTab realStatus={realStatus} />}
            {activeTab === 'wuwa-db' && <WuWaTab />}
            {activeTab === 'cloud' && <CloudTab />}
            {activeTab === 'hand-motion' && <HandMotionTab handMotionStatus={handMotionStatus} />}
            {activeTab === 'stream' && <StreamTab />}
            {activeTab === 'settings' && (
              <SettingsTab 
                sidebarMode={sidebarMode} 
                autoHideSidebar={autoHideSidebar}
                setAutoHideSidebar={setAutoHideSidebar}
                autoHideTitlebar={autoHideTitlebar}
                setAutoHideTitlebar={setAutoHideTitlebar}
                onSkinUpdated={(cfg) => {
                  const normalized = normalizeSkinConfig(cfg);
                  setSkinConfig(normalized);
                  applySkin(normalized);
                }}
              />
            )}
          </div>
        </div>

        {/* Modal de Confirmação ao Fechar */}
        <CloseConfirmModal 
          isOpen={showCloseConfirm}
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
};

export default App;
