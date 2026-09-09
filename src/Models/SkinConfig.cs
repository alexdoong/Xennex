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
    }
}
