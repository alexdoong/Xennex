using System;
using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using System.Windows.Interop;
using Microsoft.Web.WebView2.Core;
using WacomRealController;
using Xennex.Interop;
using System.Drawing;
using System.Windows.Forms;
using Point = System.Drawing.Point;
using System.Runtime.InteropServices;

namespace Xennex.UI
{
    public partial class MainWindow : Window
    {
        private WacomService wacomService;
        private RealEngineService realEngineService;
        private ConfigService configService;
        private ApiBridge apiBridge;
        private NotifyIcon notifyIcon;

        [DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
        [DllImport("user32.dll")]
        public static extern bool ReleaseCapture();

        public const int WM_NCLBUTTONDOWN = 0xA1;
        public const int HT_CAPTION = 0x2;

        private bool isSidebarMode = false;
        private bool isSlidOut = false;
        private DispatcherTimer slideTimer;
        private DispatcherTimer statusTimer;

        public MainWindow()
        {
            InitializeComponent();
            wacomService = new WacomService();
            realEngineService = new RealEngineService();
            configService = new ConfigService();
            
            InitializeApiBridge();
            InitializeTrayIcon();
            InitializeAsync();

            this.Loaded += MainWindow_Loaded;
            this.Closing += MainWindow_Closing;
        }

        private void InitializeApiBridge()
        {
            apiBridge = new ApiBridge(wacomService, realEngineService, configService);
            apiBridge.MinimizeToTrayRequested = () => this.WindowState = WindowState.Minimized;
            apiBridge.ShutdownRequested = CloseRequestedFromWeb;
            apiBridge.ToggleSidebarModeRequested = ToggleSidebarMode;
            apiBridge.IsSidebarModeGetter = () => isSidebarMode;
        }

        private async void InitializeAsync()
        {
            var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Path.GetTempPath(), "XennexWebView2"));
            await webView.EnsureCoreWebView2Async(env);
            
            webView.CoreWebView2.AddHostObjectToScript("api", apiBridge);
            
            string indexPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "wwwroot", "index.html");
            webView.CoreWebView2.Navigate("file:///" + indexPath.Replace("\\", "/"));
            
            // Background is solid now to fix input bug
            webView.DefaultBackgroundColor = System.Drawing.Color.FromArgb(255, 14, 14, 16);

            // Handle script messages for window drag
            webView.CoreWebView2.WebMessageReceived += CoreWebView2_WebMessageReceived;
        }

        private void CoreWebView2_WebMessageReceived(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (e.TryGetWebMessageAsString() == "dragWindow")
            {
                if (!isSidebarMode)
                {
                    ReleaseCapture();
                    SendMessage(new WindowInteropHelper(this).Handle, WM_NCLBUTTONDOWN, HT_CAPTION, 0);
                }
            }
        }

        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            // Restore position if valid
            if (configService.Config.WindowLeft != -1 && configService.Config.WindowTop != -1)
            {
                this.Left = configService.Config.WindowLeft;
                this.Top = configService.Config.WindowTop;
            }
            else
            {
                this.Left = (SystemParameters.WorkArea.Width - this.Width) / 2;
                this.Top = (SystemParameters.WorkArea.Height - this.Height) / 2;
            }

            slideTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(16) };
            slideTimer.Tick += SlideTimer_Tick;
            slideTimer.Start();

            statusTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
            statusTimer.Tick += (s, ev) => 
            {
                if (webView.CoreWebView2 != null)
                {
                    bool isRunning = realEngineService.IsRunning;
                    webView.CoreWebView2.ExecuteScriptAsync($"if(window.updateRealStatus) window.updateRealStatus({isRunning.ToString().ToLower()});");
                }
            };
            statusTimer.Start();
        }

        private void ToggleSidebarMode()
        {
            if (!isSidebarMode)
            {
                // Save current position before going into sidebar
                configService.Config.WindowLeft = this.Left;
                configService.Config.WindowTop = this.Top;
                configService.SaveConfig();
            }

            isSidebarMode = !isSidebarMode;
            if (isSidebarMode)
            {
                // Compact: keep normal height, snap to middle-right of screen
                var scr = Screen.PrimaryScreen;
                this.Left = scr.WorkingArea.Right - this.Width;
                this.Topmost = true;
            }
            else
            {
                this.Topmost = false;
                // Restore position
                if (configService.Config.WindowLeft != -1 && configService.Config.WindowTop != -1)
                {
                    this.Left = configService.Config.WindowLeft;
                    this.Top = configService.Config.WindowTop;
                }
                else
                {
                    this.Left = (SystemParameters.WorkArea.Width - this.Width) / 2;
                    this.Top = (SystemParameters.WorkArea.Height - this.Height) / 2;
                }
            }
            
            if (webView.CoreWebView2 != null)
            {
                webView.CoreWebView2.ExecuteScriptAsync($"if(window.updateSidebarMode) window.updateSidebarMode({isSidebarMode.ToString().ToLower()});");
            }
        }

        private void SlideTimer_Tick(object sender, EventArgs e)
        {
            if (!isSidebarMode) return;
            
            var scr = Screen.PrimaryScreen;
            double destShow = scr.WorkingArea.Right - this.Width;
            double destHide = scr.WorkingArea.Right - (configService.Config.HideSidebarPullTab ? 0 : 26);
            
            Point mouse = System.Windows.Forms.Cursor.Position;
            var windowRect = new System.Drawing.Rectangle((int)this.Left, (int)this.Top, (int)this.Width, (int)this.Height);
            
            bool mouseOver = windowRect.Contains(mouse);
            
            if (isSlidOut)
            {
                if (configService.Config.HideSidebarPullTab)
                {
                    var edgeRect = new System.Drawing.Rectangle(scr.WorkingArea.Right - 10, scr.WorkingArea.Top, 10, scr.WorkingArea.Height);
                    mouseOver = edgeRect.Contains(mouse);
                }
                else
                {
                    var pullTabRect = new System.Drawing.Rectangle(scr.WorkingArea.Right - 26, scr.WorkingArea.Top + (scr.WorkingArea.Height - 100) / 2, 26, 100);
                    mouseOver = pullTabRect.Contains(mouse);
                }
            }

            double dest = mouseOver ? destShow : destHide;
            double SLIDE_SPEED = 30;

            if (this.Left < dest)
            {
                this.Left = Math.Min(dest, this.Left + SLIDE_SPEED);
                if (this.Left == destHide) isSlidOut = true;
            }
            else if (this.Left > dest)
            {
                this.Left = Math.Max(dest, this.Left - SLIDE_SPEED);
                if (this.Left == destShow) isSlidOut = false;
            }
        }

        private void InitializeTrayIcon()
        {
            notifyIcon = new NotifyIcon
            {
                Icon = SystemIcons.Application,
                Visible = true,
                Text = "Xennex Utility Hub"
            };
            
            var menu = new ContextMenuStrip();
            menu.Items.Add("Open", null, (s, e) => RestoreFromTray());
            menu.Items.Add("Enable Wacom", null, (s, e) => wacomService.EnableDrivers());
            menu.Items.Add("Disable Wacom", null, (s, e) => wacomService.DisableDrivers());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Exit", null, (s, e) => ShutdownApp());
            
            notifyIcon.ContextMenuStrip = menu;
            notifyIcon.DoubleClick += (s, e) => RestoreFromTray();
        }

        private void MinimizeToTray()
        {
            this.Hide();
            notifyIcon.Visible = true;
        }

        private void RestoreFromTray()
        {
            this.Show();
            this.WindowState = WindowState.Normal;
            this.Activate();
        }

        private void CloseRequestedFromWeb()
        {
            if (configService.Config.CloseToTray)
            {
                MinimizeToTray();
            }
            else
            {
                ShutdownApp();
            }
        }

        private void ShutdownApp()
        {
            if (!isSidebarMode)
            {
                configService.Config.WindowLeft = this.Left;
                configService.Config.WindowTop = this.Top;
                configService.SaveConfig();
            }
            realEngineService.Stop();
            System.Windows.Application.Current.Shutdown();
        }

        private void MainWindow_Closing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            if (configService.Config.CloseToTray)
            {
                e.Cancel = true;
                MinimizeToTray();
                return;
            }
            realEngineService.Stop();
            notifyIcon.Dispose();
        }
    }
}
