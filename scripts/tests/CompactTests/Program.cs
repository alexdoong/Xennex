using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Interop;
using Xennex.Services;
using Forms = System.Windows.Forms;

class Program
{
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
    [StructLayout(LayoutKind.Sequential)] struct NativeRect { public int Left, Top, Right, Bottom; }
    static int checks;
    static void Check(bool condition, string label) { if (!condition) throw new Exception(label); checks++; }

    [STAThread]
    static void Main(string[] args)
    {
        var area = new Rectangle(0,0,1920,1080);
        Check(CompactDockGeometry.Calculate(area,360,680,"MiddleLeft",1,160,0).EffectiveCollapseEdge=="Top","Auto uses closest top edge");
        Check(CompactDockGeometry.Calculate(area,360,680,"TopLeft",1,0,100).EffectiveCollapseEdge=="Left","Auto uses closest left edge");
        Check(CompactDockGeometry.Calculate(area,360,680,"TopLeft",1,1500,100).EffectiveCollapseEdge=="Right","Auto uses closest right edge");
        Check(CompactDockGeometry.Calculate(area,360,680,"TopLeft",1,1500,100,"Top").EffectiveCollapseEdge=="Top","explicit override remains");
        foreach (int fps in new[] { 30, 60, 120 })
        {
            var cadence = new CompactFrameCadence();
            int frames = 0;
            for (int ms = 0; ms < 1000; ms++) if (cadence.ShouldRender(ms, fps)) frames++;
            Check(frames == fps, "FPS budget over one second: " + fps);
            Check(cadence.ShouldRender(2000, fps), "late frame is presented");
            Check(!cadence.ShouldRender(2000, fps), "no catch-up burst after stall");
        }
        var automatic = new CompactFrameCadence();
        Check(automatic.ShouldRender(0,0) && automatic.ShouldRender(2,0), "automatic follows render callbacks");
        Check(automatic.ShouldRender(3,30) && !automatic.ShouldRender(4,30), "FPS changes reset cadence");
        var settings = new ConfigService(); // Test output directory, never personal Data.
        foreach (int fps in new[] { 30, 60, 120, 0 })
        {
            settings.SetSidebarAnimationFps(fps);
            Check(new ConfigService().Config.SidebarAnimationFps == fps, "FPS persists: " + fps);
        }
        try { settings.SetSidebarAnimationFps(55); Check(false, "reject invalid FPS"); }
        catch (ArgumentOutOfRangeException) { Check(true, "reject invalid FPS"); }
        var motion = new CompactMotion();
        motion.Reset(0);
        Check(motion.Update(false,0,true)==1,"closing begins without jump");
        double last=1;
        for(int ms=16;ms<240;ms+=16) {
            double current=motion.Update(false,ms,true);
            Check(current<last && current>=0,"closing is monotonic"); last=current;
        }
        Check(motion.Update(false,240,true)==0,"animation ends at bounded duration");
        motion.Update(true,300,true);
        double beforeReverse=motion.Update(true,380,true);
        Check(Math.Abs(motion.Update(false,380,true)-beforeReverse)<0.00001,"reverse preserves position");
        Check(motion.Update(true,400,false)==1,"reduced motion snaps directly");
        foreach (var work in new[] { new Rectangle(0,0,1920,1040), new Rectangle(-2560,-200,2560,1400), new Rectangle(1920,0,3840,2100) })
        foreach (double scale in new[] { 1.0, 1.25, 1.5, 2.0 })
        foreach (string position in new[] { "TopLeft", "MiddleLeft", "MiddleRight" })
        foreach (int inset in new[] { 0, 160, 2000 })
        foreach (int vertical in new[] { -1, 0, 25, 100 })
        foreach (string collapse in new[] { "Auto", "Top", "Left", "Right" })
        {
            int width = (int)(360 * scale), height = Math.Min((int)(680 * scale), work.Height);
            var g = CompactDockGeometry.Calculate(work, width, height, position, scale, inset, vertical, collapse);
            Check(g.ShownRect.Left >= work.Left && g.ShownRect.Right <= work.Right, "fully visible on selected screen");
            Check(g.ShownRect.Top >= work.Top && g.ShownRect.Bottom <= work.Bottom, "fits working height");

            var hiddenVisible = Rectangle.Intersect(work, g.HiddenRect);
            if (g.EffectiveCollapseEdge == "Top")
            {
                Check(hiddenVisible.Height == g.HiddenRect.Height, "horizontal handle remains");
                Check(g.HiddenRect.Top == work.Top, "top handle at work.Top");
                Check(g.HiddenRect.Left == g.ShownRect.Left, "top handle retains horizontal position");
            }
            else
            {
                Check(hiddenVisible.Width == g.HiddenRect.Width, "vertical handle remains");
                if (g.EffectiveCollapseEdge == "Left") Check(g.HiddenRect.Left == work.Left, "left handle on monitor edge");
                else Check(g.HiddenRect.Right == work.Right, "right handle on monitor edge");
            }

            for (double t = 0.0; t <= 1.0; t += 0.05)
            {
                var r = g.GetInterpolatedRect(t);
                Check(r.Left >= work.Left && r.Right <= work.Right, "frame stays within horizontal monitor bounds");
                Check(r.Top >= work.Top && r.Bottom <= work.Bottom, "frame stays within vertical monitor bounds");
            }
        }
        if (Array.IndexOf(args, "--geometry-only") >= 0) { Console.WriteLine("PASS compact geometry: " + checks + " checks"); return; }

        var app = new System.Windows.Application();
        var window = new Window
        {
            Width = 800, Height = 600, MinWidth = 600, MinHeight = 450,
            WindowStyle = WindowStyle.None, AllowsTransparency = true, ShowInTaskbar = false, ShowActivated = false, Left = 60, Top = 60
        };
        var config = new ConfigService(); // test executable's own bin/Data
        int notifications = 0;
        var sidebar = new SidebarService(window, config, _ => notifications++);
        System.Drawing.Point simulatedCursor = new System.Drawing.Point(500, 500);
        sidebar.CursorProvider = () =>
        {
            var p = Forms.Cursor.Position;
            return (p.X != 0 || p.Y != 0) ? p : simulatedCursor;
        };
        void MoveCursor(int x, int y)
        {
            SetCursorPos(x, y);
            simulatedCursor = new System.Drawing.Point(x, y);
        }

        var cursor = Forms.Cursor.Position;
        window.Loaded += async (_, _) =>
        {
            try
            {
                var handle = new WindowInteropHelper(window).Handle;
                foreach (var screen in Forms.Screen.AllScreens)
                {
                    var work = screen.WorkingArea;
                    window.Left = work.Left + 60; window.Top = work.Top + 60;
                    await Task.Delay(100);
                    GetWindowRect(handle, out var before);
                    MoveCursor(work.Left + work.Width / 2, work.Top + work.Height / 2);
                    foreach (string pos in new[] { "MiddleRight", "MiddleLeft", "TopLeft" })
                    {
                        config.Config.SidebarPosition = pos;
                        config.Config.SidebarCollapseEdge = "Auto";
                        sidebar.ToggleSidebarMode();
                        await Task.Delay(100);
                        Check(window.ActualWidth <= 360, "WPF minimum does not coerce compact width");
                        Check(window.MinWidth == 0 && window.Topmost, "compact constraints");
                        sidebar.SetPinned(true);
                        await Task.Delay(1700);
                        GetWindowRect(handle, out var shown);
                        Check(shown.Left >= work.Left && shown.Right <= work.Right, "pinned panel remains on screen");
                        sidebar.SetPinned(false);
                        await Task.Delay(1800);
                        GetWindowRect(handle, out var hidden);

                        if (pos == "TopLeft")
                        {
                            int visHeight = Rectangle.Intersect(work, new Rectangle(hidden.Left, hidden.Top, hidden.Right - hidden.Left, hidden.Bottom - hidden.Top)).Height;
                            Check(visHeight < 40 && hidden.Bottom - hidden.Top < 40, "native viewport shrinks to horizontal handle on top");
                            Check(hidden.Top >= work.Top && hidden.Bottom <= work.Bottom, $"hidden top window never leaves monitor: ({hidden.Top},{hidden.Bottom}) work=({work.Top},{work.Bottom})");
                            MoveCursor(hidden.Left + 50, work.Top + 4);
                        }
                        else
                        {
                            int visWidth = Rectangle.Intersect(work, new Rectangle(hidden.Left, hidden.Top, hidden.Right - hidden.Left, hidden.Bottom - hidden.Top)).Width;
                            Check(visWidth < 40 && hidden.Right - hidden.Left < 40, "native viewport shrinks to handle");
                            Check(hidden.Left >= work.Left && hidden.Right <= work.Right, $"hidden window never enters neighboring monitor: {pos} ({hidden.Left},{hidden.Right}) work=({work.Left},{work.Right})");
                            MoveCursor(pos == "MiddleRight" ? work.Right - 3 : work.Left + 3, hidden.Top + 100);
                        }

                        await Task.Delay(600);
                        GetWindowRect(handle, out var revealed);
                        if (pos == "TopLeft") Check(Math.Abs(revealed.Top - shown.Top) <= 4, "edge hover reveals top panel");
                        else Check(Math.Abs(revealed.Left - shown.Left) <= 4, "edge hover reveals panel");

                        MoveCursor(work.Left + work.Width / 2, work.Top + work.Height / 2);
                        sidebar.ToggleSidebarMode();
                        GetWindowRect(handle, out var after);
                        Check(window.MinWidth == 600 && window.MinHeight == 450 && !window.Topmost, "restores constraints and topmost");
                        Check(after.Left == before.Left && after.Top == before.Top && after.Right == before.Right && after.Bottom == before.Bottom, "restores original native bounds");
                    }
                }

                config.Config.SidebarPosition = "TopLeft";
                config.Config.SidebarCollapseEdge = "Top";
                sidebar.SetPlacement(160, 0);
                sidebar.ToggleSidebarMode();
                sidebar.SetPinned(true);
                await Task.Delay(150);
                GetWindowRect(handle, out var custom);
                var customWork = Forms.Screen.FromHandle(handle).WorkingArea;
                var dpi = System.Windows.Media.VisualTreeHelper.GetDpi(window).DpiScaleX;
                Check(Math.Abs(custom.Left - customWork.Left - 160 * dpi) <= 1, "custom horizontal inset");
                Check(custom.Top == customWork.Top, "custom top alignment");
                sidebar.SetPlacement(2000, 100);
                await Task.Delay(100);
                GetWindowRect(handle, out var limited);
                Check(limited.Right <= customWork.Right && limited.Left >= customWork.Left && limited.Bottom <= customWork.Bottom, "custom placement clamps to monitor");
                var reloaded = new ConfigService();
                Check(reloaded.Config.SidebarInset == 2000 && reloaded.Config.SidebarVerticalPercent == 100, "custom position persisted");
                Check(reloaded.Config.SidebarCollapseEdge == "Top", "collapse edge persisted");
                sidebar.ToggleSidebarMode();
                sidebar.SetPlacement(0, -1);
                window.WindowState = WindowState.Maximized;
                sidebar.ToggleSidebarMode(); sidebar.ToggleSidebarMode();
                Check(window.WindowState == WindowState.Maximized, "restores maximized state");
                Check(notifications == Forms.Screen.AllScreens.Length * 6 + 4, "one state callback per transition");
                Console.WriteLine("PASS compact: " + checks + " geometry/native checks");
            }
            catch (Exception e) { Console.Error.WriteLine(e); Environment.ExitCode = 1; }
            finally { sidebar.Stop(); MoveCursor(cursor.X, cursor.Y); window.Close(); }
        };
        app.Run(window);
    }
}
