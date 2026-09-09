namespace Xennex
{
    public class AppConfig
    {
        public string RealExePath { get; set; } = "";
        public bool CloseToTray { get; set; } = true;
        public bool AutoStart { get; set; } = false;
        public int SidebarMonitorIndex { get; set; } = 0;
        public string SidebarPosition { get; set; } = "Right";
        public bool HideSidebarPullTab { get; set; } = false;
        public int HandMotionCameraIndex { get; set; } = 0;
        
        // Cloud BYOD (Bring Your Own Database) Config
        public string CloudProjectId { get; set; } = "";
        public string CloudApiKey { get; set; } = "";

        // Skin System
        public string ActiveSkin { get; set; } = "default";

        // UI Layout Configs
        public bool AutoHideSidebar { get; set; } = true;
        public bool AutoHideTitlebar { get; set; } = true;

        // Window Position
        public double WindowLeft { get; set; } = -1;
        public double WindowTop { get; set; } = -1;
    }
}


