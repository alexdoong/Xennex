export interface SkinConfig {
  backgroundFit: string;
  backgroundPositionX: number;
  backgroundPositionY: number;
  backgroundBrightness: number;
  backgroundSaturation: number;
  overlayColor: string;
  overlayOpacity: number;
  gradientColor: string;
  gradientAngle: number;
  pauseBackgroundVideo: boolean;
  panelColor: string;
  panelOpacity: number;
  panelBlur: number;
  glassHighlight: number;
  panelRadius: number;
  panelPadding: number;
  shadowStrength: number;
  inputColor: string;
  secondaryTextColor: string;
  buttonTextColor: string;
  buttonRadius: number;
  contentScale: number;
  contentPadding: number;
  fontFamily: string;
  reducedMotion: boolean;
  sidebarWidth: number;
  sidebarRadius: number;
  sidebarImageOpacity: number;
  titlebarImageOpacity: number;
  barBlur: number;
  windowRadius: number;
  navigationPlacement: 'left' | 'right' | 'bottom';
  controlsPlacement: 'left' | 'center' | 'right';
  windowPresentation: 'floating' | 'filled';
  surfaceStyle: 'glass' | 'liquid' | 'solid' | 'terminal' | 'ornate';
  navigationOrder: string[];
  cardColor: string;
  cardOpacity: number;
  cardBorderColor: string;
  cardBorderOpacity: number;
  cardRadius: number;
  cardPadding: number;
  cardGap: number;
  settingsColumns: number;
  settingsSectionOrder: string[];
  scrollbarWidth: number;
  scrollbarColor: string;
  name: string;
  backgroundType: 'image' | 'video' | 'color' | 'gradient';
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

/** JSON returned by ApiBridge.CheckForUpdates (C# UpdateCheckResult). */
export interface UpdateCheckResult {
  Success: boolean;
  HasUpdate: boolean;
  CurrentVersion: string;
  LatestVersion: string;
  ReleaseTitle: string;
  ReleaseNotes: string;
  HtmlUrl: string;
  DownloadUrl: string;
  AssetSize: number;
  ErrorMessage: string;
}

declare global {
  interface Window {
    chrome: {
      webview: {
        postMessage(message: string): void;
        hostObjects: {
          api: {
            /** Local game library and version-3 GameDocument JSON (imports also accept versions 1 and 2). Imports create an independent copy. */
            GetGameLibrary(): Promise<string>;
            SaveGame(json: string): Promise<string>;
            ImportGame(json: string): Promise<string>;
            /** Local visual library. Roots are chosen through the native folder picker. */
            GetAssetRoots(): Promise<string>;
            IsAssetIndexPaused(): Promise<boolean>;
            SetAssetIndexPaused(paused: boolean): Promise<void>;
            PickAndAddAssetRoot(): Promise<string>;
            PickRelinkAssetRoot(rootId: string): Promise<string>;
            ConfirmAssetRootRelink(planId: string): Promise<string>;
            QueryAssets(json: string): Promise<string>;
            GetAssetDetails(id: string): Promise<string>;
            /** Validated IDs, or mode=library with AssetQuery and gallery/explorer view; no desktop capture. */
            StartAssetVr(json: string): Promise<string>;
            GetAssetVrState(): Promise<string>;
            ControlAssetVr(action: string): Promise<void>;
            StopAssetVr(): Promise<void>;
            GetAssetTags(): Promise<string>;
            GetAssetTagOverview(json: string): Promise<string>;
            GetAssetCollections(): Promise<string>;
            GetSavedAssetQueries(): Promise<string>;
            SaveAssetQuery(name: string, json: string): Promise<string>;
            AddAssetCollection(name: string): Promise<string>;
            SetAssetCollectionItem(collectionId: string, assetId: string, present: boolean): Promise<void>;
            EditAsset(json: string): Promise<string>;
            EditAssets(json: string): Promise<void>;
            StartAssetIndex(rootId: string): Promise<string>;
            GetAssetJob(id: string): Promise<string>;
            CancelAssetIndex(id: string): Promise<void>;
            GetAssetMediaUrl(id: string, variant: string): Promise<string>;
            BackupAssetLibrary(): Promise<string>;
            /** Previews ordered naming rules and conflict choices off the UI thread; never mutates files. */
            PlanAssetFileOperation(json: string): Promise<string>;
            ExecuteAssetFileOperation(planId: string): Promise<string>;
            GetRecentAssetFileOperations(): Promise<string>;
            UndoAssetFileOperation(operationId: string): Promise<void>;
            /** Private local AI state/settings JSON; resource policy and FIFO run in the backend. */
            GetAiState(): Promise<string>;
            /** Explicit experimental Alice session; no autostart or live sensors. */
            GetAliceState(): Promise<string>;
            StartAliceSession(json: string): Promise<void>;
            StopAliceSession(): Promise<void>;
            SendAliceMessage(json: string): Promise<string>;
            PerceiveAliceFile(modality: string, path: string): Promise<string>;
            /** Publishes an explicitly selected image and audio clip as one sensory moment. */
            PerceiveAlicePair(image: string, audio: string): Promise<string>;
            /** Publishes a WAV for isolated word practice. An empty word requests recognition. */
            PerceiveAliceWordAudio(path: string, word: string): Promise<string>;
            /** Publishes the typed message as an actual native text signal. */
            PerceiveAliceText(text: string): Promise<string>;
            PickAlicePath(kind: string): Promise<string>;
            RefreshAiResources(): Promise<string>;
            SaveAiSettings(json: string): Promise<string>;
            DetectAiRuntime(): Promise<string>;
            StartAiRuntime(): Promise<string>;
            ReleaseAiModel(): Promise<string>;
            GetAiModels(): Promise<string>;
            SaveAiSpecialist(json: string): Promise<string>;
            CreateAiProject(title: string): Promise<string>;
            SaveAiProject(id: string, json: string): Promise<void>;
            SaveAiNote(id: string, revision: number, json: string): Promise<void>;
            ExportAiNotebook(id: string, specialistId: string): Promise<string>;
            RunAiProject(id: string, json: string): Promise<string>;
            ReviewAiRun(id: string, runId: string, score: number, interventions: number, review: string): Promise<void>;
            CreateAiChat(): Promise<string>;
            DeleteAiChat(id: string): Promise<void>;
            SendAiMessage(id: string, text: string): Promise<string>;
            CancelAiJob(id: string): Promise<void>;
            PauseAiQueue(paused: boolean): Promise<void>;
            EnableWacom(): Promise<void>;
            DisableWacom(): Promise<void>;
            IsWacomActive(): Promise<boolean>;
            StartReal(): Promise<void>;
            StopReal(): Promise<void>;
            IsRealRunning(): Promise<boolean>;
            StartHandMotion(): Promise<void>;
            StopHandMotion(): Promise<void>;
            IsHandMotionRunning(): Promise<boolean>;
            GetGestureConfig(): Promise<string>;
            GetGestureStatus(): Promise<string>;
            SaveGestureConfig(json: string): Promise<void>;
            SetGestureControl(enabled: boolean): Promise<void>;
            RecordGestureSample(id: string): Promise<void>;
            CancelGestureRecording(): Promise<void>;
            ClearGestureSamples(id: string): Promise<void>;
            ToggleSidebar(): Promise<void>;
            IsSidebarMode(): Promise<boolean>;
            SetSidebarPinned(value: boolean): Promise<void>;
            IsSidebarPinned(): Promise<boolean>;
            GetSidebarInset(): Promise<number>;
            GetSidebarVerticalPercent(): Promise<number>;
            SetSidebarPlacement(inset: number, verticalPercent: number): Promise<void>;
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
            GetSidebarAnimationFps(): Promise<number>;
            SetSidebarAnimationFps(value: number): Promise<void>;
            GetSidebarCollapseEdge(): Promise<string>;
            SetSidebarCollapseEdge(value: string): Promise<void>;
            SetCompactInteracting(interacting: boolean): Promise<void>;
            GetHandMotionCameraIndex(): Promise<number>;
            SetHandMotionCameraIndex(value: number): Promise<void>;
            GetAvailableSkins(): Promise<string[]>;
            GetActiveSkinConfig(): Promise<string>;
            GetSkinConfig(skinName: string): Promise<string>;
            SaveSkinConfig(skinName: string, json: string): Promise<boolean>;
            SaveSkinAs(newName: string, sourceName: string, json: string): Promise<string>;
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
            GetAudioProcesses(): Promise<string>;
            StartProcessAudioCapture(pid: number): Promise<boolean>;
            StopProcessAudioCapture(): Promise<void>;
            IsProcessAudioCapturing(): Promise<boolean>;
            GetCapturedProcessId(): Promise<number>;
            GetCaptureToken(): Promise<string>;
            TryBeginCapture(owner: string): Promise<boolean>;
            EndCapture(owner: string): Promise<void>;
            /** Reserve process audio for an owner whose video comes from getDisplayMedia. No video worker starts. */
            BeginBrowserCapture(owner: string): Promise<boolean>;
            /** Enumerate available monitor IDs; desktop capture never substitutes another monitor. */
            GetCaptureMonitors(): Promise<string>;
            BeginDesktopCapture(owner: string, display: string, fps: number, resolution: string): Promise<boolean>;
            /** Queue native startup off the UI thread; accepted does not mean ready. */
            BeginNativeCapture(owner: string, hwnd: number, pid: number, fps: number, resolution: string): Promise<boolean>;
            /** Explicit experimental OpenGL game hook, only in the selected process. */
            BeginGameCapture(owner: string, hwnd: number, pid: number, fps: number, resolution: string): Promise<boolean>;
            BeginCaptureAudio(owner: string, pid: number): Promise<boolean>;
            /** Owner-scoped { phase: idle|active|stopping, video/audio: idle|starting|ready|error }. */
            GetCaptureState(owner: string): Promise<string>;
            StopCaptureAudio(owner: string): Promise<void>;
            GetProcessAudioFormat(): Promise<string>;
            StartNativeWindowCapture(hwnd: number, pid: number, fps: number, resolution: string): Promise<boolean>;
            StopNativeWindowCapture(): Promise<void>;
            IsNativeWindowCapturing(): Promise<boolean>;
          };
        };
      };
    };
    updateRealStatus?: (isRunning: boolean) => void;
    updateHandMotionStatus?: (isRunning: boolean) => void;
    updateSidebarMode?: (isSidebar: boolean) => void;
    updateSidebarPosition?: (pos: string) => void;
    updateSidebarGeometry?: (width: number, height: number, edge: string) => void;
    updateSidebarCollapseEdge?: (edge: string) => void;
    showCloseModal?: () => void;
  }
}
