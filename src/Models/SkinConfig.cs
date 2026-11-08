namespace Xennex.Models
{
    public class SkinConfig
    {
        public string Name { get; set; } = "default";
        public string BackgroundType { get; set; } = "image"; // "image", "video", "color"
        public string BackgroundUrl { get; set; } = "https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=1920&auto=format&fit=crop";
        public string BackgroundColor { get; set; } = "#0f131a";
        public double BackgroundOpacity { get; set; } = 1.0;
        public double BackgroundBlur { get; set; } = 0.0;
        public string SidebarImage { get; set; } = "";
        public string SidebarColor { get; set; } = "hsla(220, 20%, 12%, 0.7)";
        public string TitlebarImage { get; set; } = "";
        public string TitlebarColor { get; set; } = "hsla(220, 20%, 12%, 0.7)";
        public string PrimaryColor { get; set; } = "hsl(260, 100%, 65%)";
        public string PrimaryHover { get; set; } = "hsl(260, 100%, 75%)";
        public string TextColor { get; set; } = "hsl(220, 10%, 95%)";
        public string BorderColor { get; set; } = "rgba(255, 255, 255, 0.25)";
        public double BorderOpacity { get; set; } = 0.25;
        public int BorderWidth { get; set; } = 1;
        public string BackgroundFit { get; set; } = "cover";
        public double BackgroundPositionX { get; set; } = 50;
        public double BackgroundPositionY { get; set; } = 50;
        public double BackgroundBrightness { get; set; } = 100;
        public double BackgroundSaturation { get; set; } = 100;
        public string OverlayColor { get; set; } = "#000000";
        public double OverlayOpacity { get; set; } = 0;
        public string GradientColor { get; set; } = "#503080";
        public double GradientAngle { get; set; } = 135;
        public bool PauseBackgroundVideo { get; set; } = false;
        public string PanelColor { get; set; } = "#121826";
        public double PanelOpacity { get; set; } = 0.95;
        public double PanelBlur { get; set; } = 16;
        public double GlassHighlight { get; set; } = 0.35;
        public double PanelRadius { get; set; } = 24;
        public double PanelPadding { get; set; } = 24;
        public double ShadowStrength { get; set; } = 0.5;
        public string InputColor { get; set; } = "#10131c";
        public string SecondaryTextColor { get; set; } = "#aab2c4";
        public string ButtonTextColor { get; set; } = "#ffffff";
        public double ButtonRadius { get; set; } = 12;
        public double ContentScale { get; set; } = 100;
        public double ContentPadding { get; set; } = 24;
        public string FontFamily { get; set; } = "system";
        public bool ReducedMotion { get; set; } = false;
        public double SidebarWidth { get; set; } = 68;
        public double SidebarRadius { get; set; } = 20;
        public double SidebarImageOpacity { get; set; } = 0.85;
        public double TitlebarImageOpacity { get; set; } = 0.85;
        public double BarBlur { get; set; } = 0;
        public double WindowRadius { get; set; } = 20;
        public string NavigationPlacement { get; set; } = "left";
        public string ControlsPlacement { get; set; } = "right";
        public string WindowPresentation { get; set; } = "floating";
        public string SurfaceStyle { get; set; } = "glass";
        public System.Collections.Generic.List<string> NavigationOrder { get; set; } = new() { "dashboard", "wuwa-db", "assets", "local-ai", "cloud", "stream", "hand-motion" };
        public string CardColor { get; set; } = "#ffffff";
        public double CardOpacity { get; set; } = 0.05;
        public string CardBorderColor { get; set; } = "#ffffff";
        public double CardBorderOpacity { get; set; } = 0.08;
        public double CardRadius { get; set; } = 16;
        public double CardPadding { get; set; } = 24;
        public double CardGap { get; set; } = 24;
        public int SettingsColumns { get; set; } = 1;
        public System.Collections.Generic.List<string> SettingsSectionOrder { get; set; } = new() { "behavior", "layout", "skins", "about" };
        public double ScrollbarWidth { get; set; } = 6;
        public string ScrollbarColor { get; set; } = "#777986";
        [System.Text.Json.Serialization.JsonExtensionData]
        public System.Collections.Generic.Dictionary<string, System.Text.Json.JsonElement> Extra { get; set; }
    }
}
