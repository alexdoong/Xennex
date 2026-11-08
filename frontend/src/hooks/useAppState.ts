import { useState, useEffect, useCallback, useRef } from 'react';
import { applySkinVariables, normalizeSkinConfig } from '../utils/skinUtils';
import type { SkinConfig } from '../webview';

const reportError = (error: unknown) => console.error('[App] Falha ao carregar configuração:', error);

export function useAppState() {
  const [realStatus, setRealStatus] = useState(false);
  const [handMotionStatus, setHandMotionStatus] = useState(false);
  const [sidebarMode, setSidebarMode] = useState(false);
  const [sidebarPosition, setSidebarPosition] = useState('MiddleRight');
  const [sidebarCollapseEdge, setSidebarCollapseEdge] = useState('Auto');
  const [effectiveCollapseEdge, setEffectiveCollapseEdge] = useState('Right');
  const [compactOpenWidth, setCompactOpenWidth] = useState(360);
  const [compactOpenHeight, setCompactOpenHeight] = useState(680);

  // Skin Configuration State
  const [skinConfig, setSkinConfig] = useState<SkinConfig | null>(null);

  const [skinPreview, previewSkin] = useState<SkinConfig | null>(null);
  const [skinEditorName, setSkinEditorName] = useState<string | null>(null);
  const onEditSkin = useCallback((name: string) => setSkinEditorName(current => current ?? name), []);
  const onSkinUpdated = useCallback((cfg: SkinConfig) => setSkinConfig(normalizeSkinConfig(cfg)), []);
  const displayedSkin = skinPreview ?? skinConfig;
  useEffect(() => { if (displayedSkin) applySkinVariables(displayedSkin); }, [displayedSkin]);

  // Close & Tray State
  const [closeToTray, setCloseToTray] = useState(false);

  // Auto-hide preferences
  const [autoHideSidebar, setAutoHideSidebar] = useState(true);
  const [autoHideTitlebar, setAutoHideTitlebar] = useState(true);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;

  useEffect(() => {
    window.updateRealStatus = (isRunning: boolean) => setRealStatus(isRunning);
    window.updateHandMotionStatus = (isRunning: boolean) => setHandMotionStatus(isRunning);
    window.updateSidebarMode = (isSidebar: boolean) => setSidebarMode(isSidebar);
    window.updateSidebarPosition = (pos: string) => setSidebarPosition(pos);
    window.updateSidebarCollapseEdge = (edge: string) => setSidebarCollapseEdge(edge);
    window.updateSidebarGeometry = (width: number, height: number, edge: string) => {
      setCompactOpenWidth(width);
      setCompactOpenHeight(height);
      if (edge) setEffectiveCollapseEdge(edge);
      document.documentElement.style.setProperty('--compact-open-width', `${width}px`);
      document.documentElement.style.setProperty('--compact-open-height', `${height}px`);
    };
    window.showCloseModal = () => {
      window.chrome?.webview?.postMessage('exitSidebar');
      setShowCloseConfirm(true);
    };

    if (api) {
      api.GetCloseToTray().then(val => setCloseToTray(val)).catch(reportError);
      api.GetSidebarPosition().then(pos => setSidebarPosition(pos || 'MiddleRight')).catch(reportError);
      api.GetSidebarCollapseEdge().then(edge => setSidebarCollapseEdge(edge || 'Auto')).catch(reportError);
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
      delete window.updateSidebarCollapseEdge;
      delete window.updateSidebarGeometry;
      delete window.showCloseModal;
    };
  }, [api]);

  return {
    realStatus, handMotionStatus, sidebarMode, sidebarPosition, sidebarCollapseEdge, effectiveCollapseEdge,
    compactOpenWidth, compactOpenHeight,
    skinConfig: displayedSkin, activeSkinName: skinConfig?.name ?? 'default',
    skinEditorName, setSkinEditorName, onEditSkin, previewSkin,
    closeToTray, setCloseToTray, autoHideSidebar, setAutoHideSidebar,
    autoHideTitlebar, setAutoHideTitlebar, showCloseConfirm, setShowCloseConfirm,
    api, onSkinUpdated
  };
}
