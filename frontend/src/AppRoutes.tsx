import LocalAiTab from './features/local-ai/LocalAiTab';
import DashboardTab from './features/dashboard/DashboardTab';
import GamesTab from './features/games/GamesTab';
import AssetLibraryTab from './features/assets/AssetLibraryTab';
import CloudTab from './features/cloud/CloudTab';
import SettingsTab from './features/settings/SettingsTab';
import HandMotionTab from './features/hand-motion/HandMotionTab';
import StreamTab from './features/stream/StreamTab';
import type { AppTab } from './layout/navigation';
import type { useAppState } from './hooks/useAppState';

type Props = ReturnType<typeof useAppState> & { activeTab: AppTab };

export default function AppRoutes({ activeTab, realStatus, handMotionStatus,
  sidebarMode, sidebarPosition, autoHideSidebar, setAutoHideSidebar, autoHideTitlebar,
  setAutoHideTitlebar, closeToTray, setCloseToTray, onSkinUpdated, onEditSkin, activeSkinName, skinEditorName, skinConfig }: Props) {
  return <>
            {activeTab === 'dashboard' && <DashboardTab realStatus={realStatus} />}
            <div style={{ display: activeTab === 'wuwa-db' ? 'contents' : 'none' }}><GamesTab /></div>
            <div style={{ display: activeTab === 'assets' ? 'contents' : 'none' }}><AssetLibraryTab active={activeTab === 'assets'} /></div>
            <div style={{ display: activeTab === 'local-ai' ? 'contents' : 'none' }}><LocalAiTab active={activeTab === 'local-ai'} /></div>
            {activeTab === 'cloud' && <CloudTab />}
            {activeTab === 'hand-motion' && <HandMotionTab handMotionStatus={handMotionStatus} />}
            <div style={{ display: activeTab === 'stream' ? 'contents' : 'none' }}><StreamTab /></div>
            {activeTab === 'settings' && (
              <SettingsTab activeSkinName={activeSkinName} skinConfig={skinConfig} skinEditorName={skinEditorName} onEditSkin={onEditSkin}
                sidebarMode={sidebarMode} sidebarPosition={sidebarPosition}
                autoHideSidebar={autoHideSidebar}
                setAutoHideSidebar={setAutoHideSidebar}
                autoHideTitlebar={autoHideTitlebar}
                setAutoHideTitlebar={setAutoHideTitlebar}
                closeToTray={closeToTray}
                setCloseToTray={setCloseToTray}
                onSkinUpdated={onSkinUpdated}
              />
            )}
  </>;
}
