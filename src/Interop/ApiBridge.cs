using System;
using System.Runtime.InteropServices;
using WacomRealController;

namespace Xennex.Interop
{
    [ClassInterface(ClassInterfaceType.AutoDual)]
    [ComVisible(true)]
    public class ApiBridge
    {
        private WacomService _wacomService;
        private RealEngineService _realEngineService;
        private ConfigService _configService;
        public Action MinimizeToTrayRequested;
        public Action ShutdownRequested;
        public Action ToggleSidebarModeRequested;
        public Func<bool> IsSidebarModeGetter;

        public ApiBridge(WacomService wacomService, RealEngineService realEngineService, ConfigService configService)
        {
            _wacomService = wacomService;
            _realEngineService = realEngineService;
            _configService = configService;
        }

        // Wacom
        public void EnableWacom() => _wacomService.EnableDrivers();
        public void DisableWacom() => _wacomService.DisableDrivers();

        // Real Engine
        public void StartReal() => _realEngineService.Start(_configService.Config.RealExePath);
        public void StopReal() => _realEngineService.Stop();
        public bool IsRealRunning() => _realEngineService.IsRunning;

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
        public void SetHideSidebarPullTab(bool value)
        {
            _configService.Config.HideSidebarPullTab = value;
            _configService.SaveConfig();
        }
    }
}
