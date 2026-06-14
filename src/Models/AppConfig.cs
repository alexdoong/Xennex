namespace WacomRealController
{
    public class AppConfig
    {
        public string RealExePath { get; set; } = "";
        public bool CloseToTray { get; set; } = true;
        public bool AutoStart { get; set; } = false;
        public int SidebarMonitorIndex { get; set; } = 0;
        public bool HideSidebarPullTab { get; set; } = false;
        
        // Cloud BYOD (Bring Your Own Database) Config
        public string CloudProjectId { get; set; } = "";
        public string CloudApiKey { get; set; } = "";

        // Window Position
        public double WindowLeft { get; set; } = -1;
        public double WindowTop { get; set; } = -1;
    }
}
