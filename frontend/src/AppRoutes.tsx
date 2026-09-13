import DashboardTab from './features/dashboard/DashboardTab';
import WuWaTab from './features/wuwa/WuWaTab';
import CloudTab from './features/cloud/CloudTab';
import SettingsTab from './features/settings/SettingsTab';
import HandMotionTab from './features/hand-motion/HandMotionTab';
import StreamTab from './features/stream/StreamTab';
import type { AppTab } from './layout/navigation';
import type { useAppState } from './hooks/useAppState';

type Props = ReturnType<typeof useAppState> & { activeTab: AppTab };

export default function AppRoutes({ activeTab, realStatus, handMotionStatus,
  sidebarMode, autoHideSidebar, setAutoHideSidebar, autoHideTitlebar,
  setAutoHideTitlebar, closeToTray, setCloseToTray, onSkinUpdated }: Props) {
  return <>
            {activeTab === 'dashboard' && <DashboardTab realStatus={realStatus} />}
            {activeTab === 'wuwa-db' && <WuWaTab />}
            {activeTab === 'cloud' && <CloudTab />}
            {activeTab === 'hand-motion' && <HandMotionTab handMotionStatus={handMotionStatus} />}
            <div style={{ display: activeTab === 'stream' ? 'contents' : 'none' }}><StreamTab /></div>
            {activeTab === 'settings' && (
              <SettingsTab 
                sidebarMode={sidebarMode} 
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
