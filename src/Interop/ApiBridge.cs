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
        public Action MinimizeToTrayRequested;
        public Action ShutdownRequested;
        public Action ToggleSidebarModeRequested;
        public Action SidebarPositionChangedRequested;
        public Func<bool> IsSidebarModeGetter;

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
        }

        // Wacom
        public void EnableWacom() => _wacomService.EnableDrivers();
        public void DisableWacom() => _wacomService.DisableDrivers();

        // Real Engine
        public void StartReal() => _realEngineService.Start(_configService.Config.RealExePath);
        public void StopReal() => _realEngineService.Stop();
        public bool IsRealRunning() => _realEngineService.IsRunning;

        // Hand Motion
        public void StartHandMotion() => _handMotionService.Start(_configService.Config.HandMotionCameraIndex);
        public void StopHandMotion() => _handMotionService.Stop();
        public bool IsHandMotionRunning() => _handMotionService.IsRunning;
        public void RecordHandGesture(string action) => _handMotionService.RecordGesture(action);
        public void StartRecordingGesture(string action) => _handMotionService.StartRecordingGesture(action);
        public void StopRecordingGesture() => _handMotionService.StopRecordingGesture();
        public string[] GetSavedGestures() => _handMotionService.GetSavedGestures();
        public void DeleteGesture(string name) => _handMotionService.DeleteGesture(name);
        public string GetSwipeConfig() => _handMotionService.GetSwipeConfig();
        public void SaveSwipeConfig(string json) => _handMotionService.SaveSwipeConfig(json);

        // Window Controls
        public void MinimizeToTray() => MinimizeToTrayRequested?.Invoke();
        public void Shutdown() => ShutdownRequested?.Invoke();
        public void ToggleSidebar() => ToggleSidebarModeRequested?.Invoke();
        public bool IsSidebarMode() => IsSidebarModeGetter?.Invoke() ?? false;

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

        // Skin Engine
        public string[] GetAvailableSkins() => _skinService.GetAvailableSkins();
        public string GetActiveSkinConfig() => _skinService.GetActiveSkinConfig();
        public string GetSkinConfig(string skinName) => _skinService.GetSkinConfig(skinName);
        public bool SaveSkinConfig(string skinName, string json) => _skinService.SaveSkinConfig(skinName, json);
        public bool CreateNewSkin(string newSkinName, string baseSkinName) => _skinService.CreateNewSkin(newSkinName, baseSkinName);
        public string PickAndImportAsset(string skinName, string assetType) => _skinService.PickAndImportAsset(skinName, assetType);
        public void OpenSkinFolder() => _skinService.OpenSkinFolder();
        public string GetActiveSkin() => _configService.Config.ActiveSkin;
        public void SetActiveSkin(string val)
        {
            _configService.Config.ActiveSkin = val;
            _configService.SaveConfig();
        }
        public void SetSidebarPosition(string val)
        {
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
        public void OpenBrowser(string url)
        {
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch { }
        }

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
            catch { }
        }


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
            catch { }
        }

        public bool IsNativeWindowCapturing() => _streamService.IsNativeCaptureRunning();

        public bool IsProcessAudioCapturing() => _processAudioCaptureService?.IsCapturing ?? false;
        public int GetCapturedProcessId() => _processAudioCaptureService?.CapturedPid ?? 0;
    }
}