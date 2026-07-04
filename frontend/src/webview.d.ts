export {};

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
            ToggleSidebar(): Promise<void>;
            MinimizeToTray(): Promise<void>;
            Shutdown(): Promise<void>;
            GetCloseToTray(): Promise<boolean>;
            SetCloseToTray(value: boolean): Promise<void>;
            GetHideSidebarPullTab(): Promise<boolean>;
            SetHideSidebarPullTab(value: boolean): Promise<void>;
            GetCloudProjectId(): Promise<string>;
            SetCloudProjectId(value: string): Promise<void>;
            GetCloudApiKey(): Promise<string>;
            SetCloudApiKey(value: string): Promise<void>;
          };
        };
      };
    };
    updateRealStatus: (isRunning: boolean) => void;
    updateSidebarMode: (isSidebar: boolean) => void;
  }
}
