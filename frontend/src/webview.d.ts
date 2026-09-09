export {};

export interface SkinConfig {
  name: string;
  backgroundType: 'image' | 'video' | 'color';
  backgroundUrl: string;
  backgroundColor: string;
  backgroundOpacity: number;
  backgroundBlur: number;
  sidebarImage: string;
  sidebarColor: string;
  titlebarImage: string;
  titlebarColor: string;
  primaryColor: string;
  primaryHover: string;
  textColor: string;
  borderColor?: string;
  borderOpacity?: number;
  borderWidth?: number;
}

declare global {
  interface Window {
    chrome: {
      webview: {
        postMessage(message: string): void;
        hostObjects: {
          api: {
            EnableWacom(): Promise<void>;
            DisableWacom(): Promise<void>;
            StartReal(): Promise<void>;
            StopReal(): Promise<void>;
            StartHandMotion(): Promise<void>;
            StopHandMotion(): Promise<void>;
            RecordHandGesture(action: string): Promise<void>;
            StartRecordingGesture(action: string): Promise<void>;
            StopRecordingGesture(): Promise<void>;
            GetSavedGestures(): Promise<string[]>;
            DeleteGesture(name: string): Promise<void>;
            GetSwipeConfig(): Promise<string>;
            SaveSwipeConfig(json: string): Promise<void>;
            ToggleSidebar(): Promise<void>;
            IsSidebarMode(): Promise<boolean>;
            MinimizeToTray(): Promise<void>;
            Shutdown(): Promise<void>;
            GetCloseToTray(): Promise<boolean>;
            SetCloseToTray(value: boolean): Promise<void>;
            GetHideSidebarPullTab(): Promise<boolean>;
            SetHideSidebarPullTab(value: boolean): Promise<void>;
            GetAutoHideSidebar(): Promise<boolean>;
            SetAutoHideSidebar(value: boolean): Promise<void>;
            GetAutoHideTitlebar(): Promise<boolean>;
            SetAutoHideTitlebar(value: boolean): Promise<void>;
            GetCloudProjectId(): Promise<string>;
            SetCloudProjectId(value: string): Promise<void>;
            GetCloudApiKey(): Promise<string>;
            SetCloudApiKey(value: string): Promise<void>;
            GetSidebarPosition(): Promise<string>;
            SetSidebarPosition(value: string): Promise<void>;
            GetHandMotionCameraIndex(): Promise<number>;
            SetHandMotionCameraIndex(value: number): Promise<void>;
            GetAvailableSkins(): Promise<string[]>;
            GetActiveSkinConfig(): Promise<string>;
            GetSkinConfig(skinName: string): Promise<string>;
            SaveSkinConfig(skinName: string, json: string): Promise<boolean>;
            CreateNewSkin(newSkinName: string, baseSkinName: string): Promise<boolean>;
            PickAndImportAsset(skinName: string, assetType: string): Promise<string>;
            OpenSkinFolder(): Promise<void>;
            GetActiveSkin(): Promise<string>;
            SetActiveSkin(value: string): Promise<void>;
            OpenStreamViewer(roomId: string, title: string): Promise<boolean>;
            CloseStreamViewer(roomId: string): Promise<boolean>;
            SetViewerAlwaysOnTop(roomId: string, val: boolean): Promise<boolean>;
            OpenBrowser(url: string): Promise<void>;
            GetAppVersion(): Promise<string>;
            CheckForUpdates(): Promise<string>;
            StartAutoUpdate(downloadUrl: string): Promise<boolean>;
          };
        };
      };
    };
    updateRealStatus: (isRunning: boolean) => void;
    updateHandMotionStatus: (isRunning: boolean) => void;
    updateSidebarMode: (isSidebar: boolean) => void;
    updateSidebarPosition: (pos: string) => void;
    showCloseModal?: () => void;
  }
}
