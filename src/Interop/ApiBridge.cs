using System;
using System.Runtime.InteropServices;
using Xennex.Services;

namespace Xennex.Interop
{
    [ClassInterface(ClassInterfaceType.AutoDual)]
    [ComVisible(true)]
    public class ApiBridge
    {
        private WacomService _wacomService;
        private RealEngineService _realEngineService;
        private ConfigService _configService;
        private SkinService _skinService;
        private HandMotionService _handMotionService;
        private StreamService _streamService;
        private UpdateService _updateService;
        private ProcessAudioCaptureService _processAudioCaptureService;
        private readonly CaptureSessionService _captureSession;
        private readonly Xennex.Services.GameAnalytics.GameAnalyticsService _games = new();
        private readonly Xennex.Services.Assets.AssetLibraryService _assets = new();
        private readonly Xennex.Services.Vr.AssetVrService _assetVr;
        private readonly Xennex.Services.LocalAi.LocalAiService _localAi = new();
        private readonly Xennex.Services.LocalAi.AlicePanelService _alice = new();
        public Action MinimizeToTrayRequested;
        public Func<string> PickAssetRootRequested;
        public Func<string> PickAssetBackupRequested;
        public Func<string, string> PickAlicePathRequested;
        public Action ShutdownRequested;
        public Action ToggleSidebarModeRequested;
        public Action SidebarPositionChangedRequested;
        public Func<bool> IsSidebarModeGetter;
        public Action<bool> SetSidebarPinnedRequested;
        public Action<int, int> SetSidebarPlacementRequested;
        public Func<bool> IsSidebarPinnedGetter;
        public Action<bool> SetCompactInteractingRequested;

        public ApiBridge(WacomService wacomService, RealEngineService realEngineService, HandMotionService handMotionService, ConfigService configService, SkinService skinService, StreamService streamService, UpdateService updateService = null, ProcessAudioCaptureService processAudioCaptureService = null)
        {
            _wacomService = wacomService;
            _realEngineService = realEngineService;
            _handMotionService = handMotionService;
            _configService = configService;
            _skinService = skinService;
            _streamService = streamService;
            _updateService = updateService ?? new UpdateService();
            _processAudioCaptureService = processAudioCaptureService ?? new ProcessAudioCaptureService();
            _captureSession = new CaptureSessionService(_streamService.StartNativeCapture,
                _processAudioCaptureService.StartCapture, _streamService.StopNativeCapture,
                _processAudioCaptureService.StopCapture, () => _processAudioCaptureService.IsRunning, _streamService.IsNativeCaptureRunning,
                _streamService.StartDesktopCapture, _streamService.StartGameCapture);
            _assetVr = new Xennex.Services.Vr.AssetVrService(_assets);
        }

        // Personal game library: validation and persistence live in the service.
        public string GetGameLibrary() => _games.GetLibrary();
        public string SaveGame(string json) => _games.SaveGame(json);
        public string ImportGame(string json) => _games.ImportGame(json);

        // Visual library: all indexing, persistence and path validation live in AssetLibraryService.
        internal Xennex.Services.Assets.AssetLibraryService Assets => _assets;
        internal void StopAssets() { _assetVr.Dispose(); _assets.Dispose(); }
        public System.Threading.Tasks.Task<string> StartAssetVr(string json) => _assetVr.Start(json);
        public string GetAssetVrState() => _assetVr.GetState();
        public void ControlAssetVr(string action) => _assetVr.Control(action);
        public System.Threading.Tasks.Task StopAssetVr() => _assetVr.Stop();
        public string GetAssetRoots() => _assets.GetRoots();
        public bool IsAssetIndexPaused() => _assets.IsIndexPaused();
        public void SetAssetIndexPaused(bool paused) => _assets.SetIndexPaused(paused);
        public string PickAndAddAssetRoot()
        {
            var path = PickAssetRootRequested?.Invoke();
            return string.IsNullOrEmpty(path) ? "" : _assets.AddRoot(path);
        }
        public System.Threading.Tasks.Task<string> PickRelinkAssetRoot(string rootId)
        {
            var path = PickAssetRootRequested?.Invoke();
            if (string.IsNullOrEmpty(path)) return System.Threading.Tasks.Task.FromResult("");
            return System.Threading.Tasks.Task.Run(() => _assets.PlanRelink(rootId, path));
        }
        public string ConfirmAssetRootRelink(string planId) => _assets.ConfirmRelink(planId);
        public System.Threading.Tasks.Task<string> QueryAssets(string json) =>
            System.Threading.Tasks.Task.Run(() => _assets.Query(json));
        public string GetAssetDetails(string id) => _assets.GetDetails(id);
          public string GetAssetTags() => _assets.GetTags();
          public System.Threading.Tasks.Task<string> GetAssetTagOverview(string json) =>
              System.Threading.Tasks.Task.Run(() => _assets.GetTagOverview(json));
        public string GetAssetCollections() => _assets.GetCollections();
        public string GetSavedAssetQueries() => _assets.GetSavedQueries();
        public string SaveAssetQuery(string name, string json) => _assets.SaveQuery(name, json);
        public string AddAssetCollection(string name) => _assets.AddCollection(name);
        public void SetAssetCollectionItem(string collectionId, string assetId, bool present) =>
            _assets.SetCollectionItem(collectionId, assetId, present);
        public string EditAsset(string json) => _assets.Edit(json);
        public void EditAssets(string json) => _assets.EditBatch(json);
        public string StartAssetIndex(string rootId) => _assets.StartIndex(rootId);
        public string GetAssetJob(string id) => _assets.GetJob(id);
        public void CancelAssetIndex(string id) => _assets.CancelIndex(id);
        public string GetAssetMediaUrl(string id, string variant) => _assets.MediaUrl(id, variant);
        public System.Threading.Tasks.Task<string> BackupAssetLibrary()
        {
            var path = PickAssetBackupRequested?.Invoke();
            if (string.IsNullOrEmpty(path)) return System.Threading.Tasks.Task.FromResult("");
            return System.Threading.Tasks.Task.Run(() => { _assets.Backup(path); return path; });
        }
        public System.Threading.Tasks.Task<string> PlanAssetFileOperation(string json) => System.Threading.Tasks.Task.Run(() => _assets.PlanFileOperation(json));
        public string ExecuteAssetFileOperation(string planId) => _assets.ExecuteFileOperation(planId);
        public string GetRecentAssetFileOperations() => _assets.GetRecentFileOperations();
        public System.Threading.Tasks.Task UndoAssetFileOperation(string operationId) => _assets.UndoFileOperation(operationId);

        // Local AI: orchestration, persistence and resource policy live in dedicated services.
        internal void StopLocalAi() => _localAi.Stop();
        internal System.Threading.Tasks.Task StopAlice() => _alice.Shutdown();
        public System.Threading.Tasks.Task<string> GetAliceState() => _alice.State();
        public System.Threading.Tasks.Task StartAliceSession(string json) => _alice.Start(json);
        public System.Threading.Tasks.Task StopAliceSession() => _alice.Stop();
        public async System.Threading.Tasks.Task<string> SendAliceMessage(string json) => (await _alice.Send(json)).GetRawText();
        public async System.Threading.Tasks.Task<string> PerceiveAliceFile(string modality, string path) => (await _alice.Perceive(modality, path)).GetRawText();
        public async System.Threading.Tasks.Task<string> PerceiveAlicePair(string image, string audio) => (await _alice.PerceivePair(image, audio)).GetRawText();
        public async System.Threading.Tasks.Task<string> PerceiveAliceWordAudio(string path, string word) => (await _alice.PerceiveWordAudio(path, word)).GetRawText();
        public async System.Threading.Tasks.Task<string> PerceiveAliceText(string text) => (await _alice.PerceiveText(text)).GetRawText();
        public string PickAlicePath(string kind) => PickAlicePathRequested?.Invoke(kind) ?? "";
        public string GetAiState() => _localAi.GetState();
        public System.Threading.Tasks.Task<string> RefreshAiResources() => _localAi.RefreshResources();
        public string SaveAiSettings(string json) => _localAi.SaveSettings(json);
        public System.Threading.Tasks.Task<string> DetectAiRuntime() => _localAi.DetectRuntime();
        public System.Threading.Tasks.Task<string> StartAiRuntime() => _localAi.StartRuntime();
        public System.Threading.Tasks.Task<string> ReleaseAiModel() => _localAi.ReleaseModel();
        public System.Threading.Tasks.Task<string> GetAiModels() => _localAi.DiscoverModels();
        public string SaveAiSpecialist(string json) => _localAi.SaveSpecialist(json);
        public string CreateAiProject(string title) => _localAi.NewProject(title);
        public void SaveAiProject(string id, string json) => _localAi.SaveProject(id, json);
        public void SaveAiNote(string id, int revision, string json) => _localAi.SaveNote(id, revision, json);
        public string ExportAiNotebook(string id, string specialistId) => _localAi.ExportNotebook(id, specialistId);
        public string RunAiProject(string id, string json) => _localAi.RunProject(id, json);
        public void ReviewAiRun(string id, string runId, int score, int interventions, string review) => _localAi.ReviewRun(id, runId, score, interventions, review);
        public string CreateAiChat() => _localAi.NewChat();
        public void DeleteAiChat(string id) => _localAi.DeleteChat(id);
        public string SendAiMessage(string id, string text) => _localAi.Send(id, text);
        public void CancelAiJob(string id) => _localAi.Cancel(id);
        public void PauseAiQueue(bool paused) => _localAi.Pause(paused);
        // Wacom
        public void EnableWacom() => _wacomService.EnableDrivers();
        public void DisableWacom() => _wacomService.DisableDrivers();
        public bool IsWacomActive() => _wacomService.QueryWacomActive();

        // Real Engine
        public void StartReal() => _realEngineService.Start(_configService.Config.RealExePath);
        public void StopReal() => _realEngineService.Stop();
        public bool IsRealRunning() => _realEngineService.IsRunning;

        // Hand Motion
        public void StartHandMotion() => _handMotionService.Start(_configService.Config.HandMotionCameraIndex);
        public void StopHandMotion() => _handMotionService.Stop();
        public bool IsHandMotionRunning() => _handMotionService.IsRunning;
        public string GetGestureConfig() => _handMotionService.GetConfig();
        public string GetGestureStatus() => _handMotionService.GetStatus();
        public void SaveGestureConfig(string json) => _handMotionService.SaveConfig(json);
        public void SetGestureControl(bool enabled) => _handMotionService.SetControl(enabled);
        public void RecordGestureSample(string id) => _handMotionService.RecordSample(id);
        public void CancelGestureRecording() => _handMotionService.CancelRecording();
        public void ClearGestureSamples(string id) => _handMotionService.ClearSamples(id);
        // Window Controls
        public void MinimizeToTray() => MinimizeToTrayRequested?.Invoke();
        public void Shutdown() => ShutdownRequested?.Invoke();
        public void ToggleSidebar() => ToggleSidebarModeRequested?.Invoke();
        public bool IsSidebarMode() => IsSidebarModeGetter?.Invoke() ?? false;
        public void SetSidebarPinned(bool value) => SetSidebarPinnedRequested?.Invoke(value);
        public bool IsSidebarPinned() => IsSidebarPinnedGetter?.Invoke() ?? false;
        public int GetSidebarInset() => _configService.Config.SidebarInset;
        public int GetSidebarVerticalPercent() => _configService.Config.SidebarVerticalPercent;
        public void SetSidebarPlacement(int inset, int verticalPercent) => SetSidebarPlacementRequested?.Invoke(inset, verticalPercent);

        // App Settings
        public bool GetCloseToTray() => _configService.Config.CloseToTray;
        public void SetCloseToTray(bool value)
        {
            _configService.Config.CloseToTray = value;
            _configService.SaveConfig();
        }
        public bool GetHideSidebarPullTab() => _configService.Config.HideSidebarPullTab;
        public void SetHideSidebarPullTab(bool val)
        {
            _configService.Config.HideSidebarPullTab = val;
            _configService.SaveConfig();
        }
        public bool GetAutoHideSidebar() => _configService.Config.AutoHideSidebar;
        public void SetAutoHideSidebar(bool val)
        {
            _configService.Config.AutoHideSidebar = val;
            _configService.SaveConfig();
        }

        public bool GetAutoHideTitlebar() => _configService.Config.AutoHideTitlebar;
        public void SetAutoHideTitlebar(bool val)
        {
            _configService.Config.AutoHideTitlebar = val;
            _configService.SaveConfig();
        }

        public string GetSidebarPosition() => _configService.Config.SidebarPosition;
        public string GetSidebarCollapseEdge() => _configService.Config.SidebarCollapseEdge;
        public void SetSidebarCollapseEdge(string val)
        {
            if (val != "Auto" && val != "Top" && val != "Left" && val != "Right")
                throw new ArgumentException("Direção de recolhimento inválida.");
            _configService.Config.SidebarCollapseEdge = val;
            _configService.SaveConfig();
            SidebarPositionChangedRequested?.Invoke();
        }
        public int GetSidebarAnimationFps() => _configService.Config.SidebarAnimationFps;
        public void SetSidebarAnimationFps(int fps) => _configService.SetSidebarAnimationFps(fps);
        public void SetCompactInteracting(bool interacting) => SetCompactInteractingRequested?.Invoke(interacting);

        // Skin Engine
        public string[] GetAvailableSkins() => _skinService.GetAvailableSkins();
        public string GetActiveSkinConfig() => _skinService.GetActiveSkinConfig();
        public string GetSkinConfig(string skinName) => _skinService.GetSkinConfig(skinName);
        public bool SaveSkinConfig(string skinName, string json) => _skinService.SaveSkinConfig(skinName, json);
        public string SaveSkinAs(string name, string source, string json) => _skinService.SaveSkinAs(name, source, json);
        public bool CreateNewSkin(string newSkinName, string baseSkinName) => _skinService.CreateNewSkin(newSkinName, baseSkinName);
        public string PickAndImportAsset(string skinName, string assetType) => _skinService.PickAndImportAsset(skinName, assetType);
        public void OpenSkinFolder() => _skinService.OpenSkinFolder();
        public string GetActiveSkin() => _configService.Config.ActiveSkin;
        public void SetActiveSkin(string val)
        {
            _skinService.SetActiveSkin(val);
        }
        public void SetSidebarPosition(string val)
        {
            if (val != "TopLeft" && val != "MiddleLeft" && val != "MiddleRight")
                throw new ArgumentException("Posição do painel inválida.");
            _configService.Config.SidebarPosition = val;
            _configService.SaveConfig();
            SidebarPositionChangedRequested?.Invoke();
        }

        public int GetHandMotionCameraIndex() => _configService.Config.HandMotionCameraIndex;
        public void SetHandMotionCameraIndex(int val)
        {
            _configService.Config.HandMotionCameraIndex = val;
            _configService.SaveConfig();
        }

        // Cloud Config
        public string GetCloudProjectId() => _configService.Config.CloudProjectId;
        public void SetCloudProjectId(string val)
        {
            _configService.Config.CloudProjectId = val;
            _configService.SaveConfig();
        }

        public string GetCloudApiKey() => _configService.Config.CloudApiKey;
        public void SetCloudApiKey(string val)
        {
            _configService.Config.CloudApiKey = val;
            _configService.SaveConfig();
        }

        // Stream Viewer Windows (P2P Pop-out)
        public bool OpenStreamViewer(string roomId, string title) => _streamService.OpenViewer(roomId, title);
        public bool CloseStreamViewer(string roomId) => _streamService.CloseViewer(roomId);
        public bool SetViewerAlwaysOnTop(string roomId, bool val) => _streamService.SetAlwaysOnTop(roomId, val);
        public void OpenBrowser(string url) => BrowserService.Open(url);

        // Updates & Versioning
        public string GetAppVersion() => UpdateService.CurrentVersion;
        public async System.Threading.Tasks.Task<string> CheckForUpdates() =>
            System.Text.Json.JsonSerializer.Serialize(await _updateService.CheckForUpdatesAsync());
        public async System.Threading.Tasks.Task<bool> StartAutoUpdate(string downloadUrl) =>
            await _updateService.StartAutoUpdateAsync(downloadUrl);

        // Process-specific Audio Capture (WASAPI Loopback)
        public string GetAudioProcesses()
        {
            try
            {
                var processes = _processAudioCaptureService.GetAvailableProcesses();
                return System.Text.Json.JsonSerializer.Serialize(processes);
            }
            catch (Exception ex)
            {
                Console.WriteLine("[ApiBridge] Erro ao obter processos de audio: " + ex.Message);
                return "[]";
            }
        }

        public bool StartProcessAudioCapture(int pid)
        {
            try
            {
                return _processAudioCaptureService.StartCapture(pid);
            }
            catch (Exception ex)
            {
                Console.WriteLine("[ApiBridge] Erro ao iniciar captura de processo: " + ex.Message);
                return false;
            }
        }

        public void StopProcessAudioCapture()
        {
            try
            {
                _processAudioCaptureService.StopCapture();
            }
            catch (Exception ex) { AppLog.Error("ApiBridge", ex); }
        }


        public string GetCaptureToken() => Xennex.Services.Security.LocalRequestPolicy.CaptureToken;

        public bool TryBeginCapture(string owner) => _captureSession.TryBegin(owner);
        public void EndCapture(string owner) => _captureSession.End(owner);
        public bool BeginBrowserCapture(string owner) => _captureSession.BeginBrowserVideo(owner);
        public string GetCaptureMonitors() => _streamService.GetCaptureMonitors();
        public bool BeginDesktopCapture(string owner, string display, int fps, string resolution) =>
            _captureSession.BeginDesktopVideo(owner, display, fps, resolution);
        public bool BeginNativeCapture(string owner, long hwnd, int pid, int fps, string resolution) =>
            _captureSession.BeginVideo(owner, hwnd, pid, fps, resolution);
        public bool BeginGameCapture(string owner, long hwnd, int pid, int fps, string resolution) =>
            _captureSession.BeginGameVideo(owner, hwnd, pid, fps, resolution);
        public bool BeginCaptureAudio(string owner, int pid) => _captureSession.BeginAudio(owner, pid);
        public string GetCaptureState(string owner) => _captureSession.GetState(owner);
        public void StopCaptureAudio(string owner) => _captureSession.StopAudio(owner);
        public string GetProcessAudioFormat() => System.Text.Json.JsonSerializer.Serialize(new {
            sampleRate = _processAudioCaptureService.SampleRate,
            channels = _processAudioCaptureService.Channels
        });

        // Native GPU Capture Worker (Windows.Graphics.Capture)
        public bool StartNativeWindowCapture(long hwnd, int pid, int fps, string resolution)
        {
            try
            {
                return _streamService.StartNativeCapture(hwnd, pid, fps, resolution);
            }
            catch (Exception ex)
            {
                Console.WriteLine("[ApiBridge] Erro ao iniciar captura nativa: " + ex.Message);
                return false;
            }
        }

        public void StopNativeWindowCapture()
        {
            try
            {
                _streamService.StopNativeCapture();
                _processAudioCaptureService.StopCapture();
            }
            catch (Exception ex) { AppLog.Error("ApiBridge", ex); }
        }

        public bool IsNativeWindowCapturing() => _captureSession.IsBusy || _streamService.IsNativeCaptureRunning();

        public bool IsProcessAudioCapturing() => _processAudioCaptureService?.IsCapturing ?? false;
        public int GetCapturedProcessId() => _processAudioCaptureService?.CapturedPid ?? 0;
    }
}
