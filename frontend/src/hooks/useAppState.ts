import { useState, useEffect, useCallback } from 'react';
import { computeBorder, normalizeSkinConfig } from '../utils/skinUtils';
import type { SkinConfig } from '../webview';

const reportError = (error: unknown) => console.error('[App] Falha ao carregar configuração:', error);

export function useAppState() {
  const [realStatus, setRealStatus] = useState(false);
  const [handMotionStatus, setHandMotionStatus] = useState(false);
  const [sidebarMode, setSidebarMode] = useState(false);
  const [sidebarPosition, setSidebarPosition] = useState('MiddleRight');

  // Skin Configuration State
  const [skinConfig, setSkinConfig] = useState<SkinConfig | null>(null);

  // Close & Tray State
  const [closeToTray, setCloseToTray] = useState(false);

  // Auto-hide preferences
  const [autoHideSidebar, setAutoHideSidebar] = useState(true);
  const [autoHideTitlebar, setAutoHideTitlebar] = useState(true);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

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
      api.GetCloseToTray().then(val => setCloseToTray(val)).catch(reportError);
      api.GetSidebarPosition().then(pos => setSidebarPosition(pos || 'MiddleRight')).catch(reportError);
      api.GetAutoHideSidebar().then(val => setAutoHideSidebar(val)).catch(reportError);
      api.GetAutoHideTitlebar().then(val => setAutoHideTitlebar(val)).catch(reportError);
      api.IsSidebarMode().then(val => setSidebarMode(val)).catch(reportError);

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
      }).catch(reportError);
    }

    return () => {
      delete window.updateRealStatus;
      delete window.updateHandMotionStatus;
      delete window.updateSidebarMode;
      delete window.updateSidebarPosition;
      delete window.showCloseModal;
    };
  }, [api, applySkin]);


  const onSkinUpdated = (cfg: SkinConfig) => {
    const normalized = normalizeSkinConfig(cfg);
    setSkinConfig(normalized);
    applySkin(normalized);
  };

  return { realStatus, handMotionStatus, sidebarMode, sidebarPosition, skinConfig,
    closeToTray, setCloseToTray, autoHideSidebar, setAutoHideSidebar,
    autoHideTitlebar, setAutoHideTitlebar, showCloseConfirm, setShowCloseConfirm,
    api, onSkinUpdated };
}
