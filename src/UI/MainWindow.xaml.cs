using System;
using System.IO;
using System.Windows;
using System.Windows.Threading;
using System.Windows.Interop;
using Microsoft.Web.WebView2.Core;
using Xennex.Services;
using Xennex.Interop;
using System.Windows.Forms;
using System.Runtime.InteropServices;
using Application = System.Windows.Application;
using MessageBox = System.Windows.MessageBox;

namespace Xennex.UI
{
    public partial class MainWindow : Window
    {
        private readonly WacomService wacomService;
        private readonly RealEngineService realEngineService;
        private readonly HandMotionService handMotionService;
        private readonly ConfigService configService;
        private readonly SkinService skinService;
        private readonly StreamService streamService;
        private readonly LocalWebServer localWebServer;
        private readonly SidebarService sidebarService;
        private ApiBridge apiBridge;
        private NotifyIcon notifyIcon;
        private DispatcherTimer statusTimer;
        private bool isForceExiting = false;

        [DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
        [DllImport("user32.dll")]
        public static extern bool ReleaseCapture();
        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);

        public const int WM_NCLBUTTONDOWN = 0xA1;
        public const int HT_CAPTION = 0x2;

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        private static extern int RegisterWindowMessage(string lpString);
                        [DllImport("user32.dll")]
        public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
        [DllImport("user32.dll")]
        public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
        [DllImport("user32.dll")]
        public static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);

        public const int GWL_STYLE = -16;
        public const int GWL_EXSTYLE = -20;
        public const int WS_EX_LAYERED = 0x80000;
        public const int WS_CAPTION = 0x00C00000;
        public const int LWA_COLORKEY = 1;

        public static readonly int WM_SHOW_XENNEX = RegisterWindowMessage("XENNEX_RESTORE_INSTANCE_MSG");
        public static CoreWebView2Environment SharedEnvironment { get; private set; }

        public MainWindow()
        {
            InitializeComponent();

            wacomService = new WacomService();
            realEngineService = new RealEngineService();
            handMotionService = new HandMotionService();
            configService = new ConfigService();
            skinService = new SkinService(configService);
            streamService = new StreamService();
            sidebarService = new SidebarService(this, configService, OnSidebarModeChanged);

            string baseDir = AppContext.BaseDirectory;
            string wwwDir = Path.Combine(baseDir, "wwwroot");
            localWebServer = new LocalWebServer(wwwDir);
            localWebServer.Start();

            InitializeApiBridge();
            InitializeTrayIcon();
            InitializeAsync();

            this.Loaded += MainWindow_Loaded;
            this.Closing += MainWindow_Closing;
        }

        private void InitializeApiBridge()
        {
            apiBridge = new ApiBridge(wacomService, realEngineService, handMotionService, configService, skinService, streamService)
            {
                MinimizeToTrayRequested = MinimizeToTray,
                ShutdownRequested = ShutdownApp,
                ToggleSidebarModeRequested = () => sidebarService.ToggleSidebarMode(),
                IsSidebarModeGetter = () => sidebarService.IsSidebarMode,
                SidebarPositionChangedRequested = () => sidebarService.OnSidebarPositionChanged()
            };
        }

        private void OnSidebarModeChanged(bool isSidebar)
        {
            webView?.CoreWebView2?.ExecuteScriptAsync(
                $"if(window.updateSidebarMode) window.updateSidebarMode({isSidebar.ToString().ToLower()});");
        }

        private async void InitializeAsync()
        {
            try
            {
                if (SharedEnvironment == null)
                {
                    SharedEnvironment = await CreateWebViewEnvironmentAsync();
                }

                await webView.EnsureCoreWebView2Async(SharedEnvironment);

                webView.CoreWebView2.AddHostObjectToScript("api", apiBridge);
                webView.CoreWebView2.PermissionRequested += (s, ev) =>
                {
                    if (ev.PermissionKind == CoreWebView2PermissionKind.Camera ||
                        ev.PermissionKind == CoreWebView2PermissionKind.Microphone ||
                        (int)ev.PermissionKind == 14)
                    {
                        ev.State = CoreWebView2PermissionState.Allow;
                    }
                };

                string baseDir = AppContext.BaseDirectory;
                string wwwrootDir = Path.Combine(baseDir, "wwwroot");

                webView.CoreWebView2.SetVirtualHostNameToFolderMapping("appassets", wwwrootDir, CoreWebView2HostResourceAccessKind.Allow);
                webView.CoreWebView2.Navigate("https://appassets/index.html");
                webView.DefaultBackgroundColor = System.Drawing.Color.Transparent;

                webView.CoreWebView2.WebMessageReceived += CoreWebView2_WebMessageReceived;
                webView.NavigationCompleted += (s, ev) =>
                {
                    this.Visibility = Visibility.Visible;
                };
            }
            catch (Exception ex)
            {
                System.Windows.Forms.MessageBox.Show(
                    $"Erro ao inicializar interface: {ex.Message}",
                    "Xennex",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private async System.Threading.Tasks.Task<CoreWebView2Environment> CreateWebViewEnvironmentAsync()
        {
            var envOptions = new CoreWebView2EnvironmentOptions("--enable-usermedia-screen-capturing");
            string userFolder = Path.Combine(Path.GetTempPath(), "XennexWebView2");
            try
            {
                return await CoreWebView2Environment.CreateAsync(null, userFolder, envOptions);
            }
            catch (COMException ex) when ((uint)ex.HResult == 0x800700AA)
            {
                string fallbackFolder = Path.Combine(Path.GetTempPath(), $"XennexWebView2_{System.Diagnostics.Process.GetCurrentProcess().Id}");
                return await CoreWebView2Environment.CreateAsync(null, fallbackFolder, envOptions);
            }
        }

        private void CoreWebView2_WebMessageReceived(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string msg = e.TryGetWebMessageAsString();
            if (msg == "dragWindow" && !sidebarService.IsSidebarMode)
            {
                ReleaseCapture();
                SendMessage(new WindowInteropHelper(this).Handle, WM_NCLBUTTONDOWN, HT_CAPTION, 0);
                return;
            }

            if (msg == "enterSidebar" && !sidebarService.IsSidebarMode)
            {
                sidebarService.ToggleSidebarMode();
                return;
            }

            if (msg == "exitSidebar" && sidebarService.IsSidebarMode)
            {
                sidebarService.ToggleSidebarMode();
            }
        }

        private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            if (msg == WM_SHOW_XENNEX)
            {
                RestoreFromTray();
                handled = true;
            }
            return IntPtr.Zero;
        }

        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            var hwnd = new WindowInteropHelper(this).Handle;
            var source = HwndSource.FromHwnd(hwnd);
            source?.AddHook(WndProc);
            RestoreWindowPosition();
            StartStatusTimer();
        }
        private void RestoreWindowPosition()
        {
            if (configService.Config.WindowLeft >= 0 && configService.Config.WindowLeft < SystemParameters.VirtualScreenWidth - 200 &&
                configService.Config.WindowTop >= 0 && configService.Config.WindowTop < SystemParameters.VirtualScreenHeight - 200)
            {
                this.Left = configService.Config.WindowLeft;
                this.Top = configService.Config.WindowTop;
                return;
            }

            this.Left = (SystemParameters.WorkArea.Width - this.Width) / 2;
            this.Top = (SystemParameters.WorkArea.Height - this.Height) / 2;
        }

        private void StartStatusTimer()
        {
            statusTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
            statusTimer.Tick += (s, ev) =>
            {
                if (webView.CoreWebView2 == null) return;

                bool isRunning = realEngineService.IsRunning;
                webView.CoreWebView2.ExecuteScriptAsync($"if(window.updateRealStatus) window.updateRealStatus({isRunning.ToString().ToLower()});");

                bool isHandMotionRunning = handMotionService.IsRunning;
                webView.CoreWebView2.ExecuteScriptAsync($"if(window.updateHandMotionStatus) window.updateHandMotionStatus({isHandMotionRunning.ToString().ToLower()});");
            };
            statusTimer.Start();
        }

        private void InitializeTrayIcon()
        {
            notifyIcon = new NotifyIcon
            {
                Icon = System.Drawing.SystemIcons.Application,
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
            this.ShowInTaskbar = false;
            notifyIcon.Visible = true;
        }

        private void RestoreFromTray()
        {
            this.Show();
            this.ShowInTaskbar = true;
            this.WindowState = WindowState.Normal;
            this.Visibility = Visibility.Visible;
            this.Activate();
            this.Focus();

            var hwnd = new WindowInteropHelper(this).Handle;
            if (hwnd != IntPtr.Zero)
            {
                SetForegroundWindow(hwnd);
            }
        }

        private void ShutdownApp()
        {
            isForceExiting = true;

            if (!sidebarService.IsSidebarMode)
            {
                configService.Config.WindowLeft = this.Left;
                configService.Config.WindowTop = this.Top;
                configService.SaveConfig();
            }

            sidebarService.Stop();
            statusTimer?.Stop();
            realEngineService.Stop();
            handMotionService.Stop();
            streamService?.CloseAllViewers();
            localWebServer?.Stop();
            notifyIcon?.Dispose();

            Application.Current.Shutdown();
        }

        private void MainWindow_Closing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            if (isForceExiting)
            {
                if (!sidebarService.IsSidebarMode)
                {
                    configService.Config.WindowLeft = this.Left;
                    configService.Config.WindowTop = this.Top;
                    configService.SaveConfig();
                }
                sidebarService.Stop();
                statusTimer?.Stop();
                realEngineService.Stop();
                handMotionService.Stop();
                streamService?.CloseAllViewers();
                notifyIcon?.Dispose();
                return;
            }

            e.Cancel = true;
            if (webView?.CoreWebView2 != null)
            {
                webView.CoreWebView2.ExecuteScriptAsync("if(window.showCloseModal) window.showCloseModal();");
                return;
            }

            var result = MessageBox.Show(
                "Deseja manter o Xennex minimizado na bandeja do sistema?\n\n- Sim: Minimizar para a bandeja\n- Não: Fechar o aplicativo completamente",
                "Xennex",
                MessageBoxButton.YesNoCancel,
                MessageBoxImage.Question);

            if (result == MessageBoxResult.Yes)
            {
                MinimizeToTray();
                return;
            }

            if (result == MessageBoxResult.No)
            {
                ShutdownApp();
            }
        }
    }
}
