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
        private sealed class DialogOwner : System.Windows.Forms.IWin32Window
        {
            public IntPtr Handle { get; }
            public DialogOwner(IntPtr handle) => Handle = handle;
        }

        private readonly WacomService wacomService;
        private readonly RealEngineService realEngineService;
        private readonly HandMotionService handMotionService;
        private readonly ConfigService configService;
        private readonly SkinService skinService;
        private readonly StreamService streamService;
        private readonly LocalWebServer localWebServer;
        private readonly SidebarService sidebarService;
        private readonly UpdateService updateService;
        private readonly ProcessAudioCaptureService processAudioCaptureService;
        private ApiBridge apiBridge;
        private NotifyIcon notifyIcon;
        private System.Drawing.Icon trayIcon;
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
        public const int HTLEFT = 10;
        public const int HTRIGHT = 11;
        public const int HTTOP = 12;
        public const int HTTOPLEFT = 13;
        public const int HTTOPRIGHT = 14;
        public const int HTBOTTOM = 15;
        public const int HTBOTTOMLEFT = 16;
        public const int HTBOTTOMRIGHT = 17;

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

        public static CoreWebView2Environment SharedEnvironment { get; private set; }

        public MainWindow()
        {
            InitializeComponent();
            Icon = AppIcon.LoadWindowIcon();

            wacomService = new WacomService();
            realEngineService = new RealEngineService();
            handMotionService = new HandMotionService();
            configService = new ConfigService();
            skinService = new SkinService(configService);
            streamService = new StreamService();
            sidebarService = new SidebarService(this, configService, OnSidebarModeChanged);
            sidebarService.OnGeometryChanged = (w, h, edge) =>
            {
                webView?.CoreWebView2?.ExecuteScriptAsync(
                    $"if(window.updateSidebarGeometry) window.updateSidebarGeometry({w}, {h}, '{edge}');");
            };
            updateService = new UpdateService();
            processAudioCaptureService = new ProcessAudioCaptureService();
            processAudioCaptureService.OnAudioChunkAvailable += (bytes, rate, ch) =>
            {
                localWebServer?.BroadcastAudioChunk(bytes, rate, ch);
            };

            string baseDir = AppContext.BaseDirectory;
            string wwwDir = Path.Combine(baseDir, "wwwroot");
            localWebServer = new LocalWebServer(wwwDir);
            localWebServer.AudioFormatProvider = () => (processAudioCaptureService.SampleRate, processAudioCaptureService.Channels);
            localWebServer.Start();

            InitializeApiBridge();
            InitializeTrayIcon();
            InitializeAsync();

            this.Loaded += MainWindow_Loaded;
            this.Closing += MainWindow_Closing;
        }

        private void InitializeApiBridge()
        {
            apiBridge = new ApiBridge(wacomService, realEngineService, handMotionService, configService, skinService, streamService, updateService, processAudioCaptureService)
            {
                MinimizeToTrayRequested = MinimizeToTray,
                ShutdownRequested = ShutdownApp,
                ToggleSidebarModeRequested = () => sidebarService.ToggleSidebarMode(),
                IsSidebarModeGetter = () => sidebarService.IsSidebarMode,
                SidebarPositionChangedRequested = () => sidebarService.OnSidebarPositionChanged(),
                SetSidebarPinnedRequested = value => sidebarService.SetPinned(value),
                IsSidebarPinnedGetter = () => sidebarService.IsPinned,
                SetSidebarPlacementRequested = (inset, vertical) => sidebarService.SetPlacement(inset, vertical),
                SetCompactInteractingRequested = val => sidebarService.SetInteracting(val),
                PickAssetRootRequested = () =>
                {
                    using var dialog = new FolderBrowserDialog { Description = "Escolha uma pasta para a Biblioteca do Xennex", UseDescriptionForTitle = true };
                    return dialog.ShowDialog(new DialogOwner(new WindowInteropHelper(this).Handle)) == System.Windows.Forms.DialogResult.OK ? dialog.SelectedPath : "";
                },
                PickAlicePathRequested = PickAlicePath,
                PickAssetBackupRequested = () =>
                {
                    using var dialog = new SaveFileDialog { Title = "Salvar backup do catálogo", Filter = "Catálogo SQLite (*.db)|*.db", FileName = "xennex-biblioteca.db", OverwritePrompt = true };
                    return dialog.ShowDialog(new DialogOwner(new WindowInteropHelper(this).Handle)) == System.Windows.Forms.DialogResult.OK ? dialog.FileName : "";
                }
            };
            streamService.ApiBridge = apiBridge;
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
                Xennex.Interop.WebViewSecurity.Configure(webView.CoreWebView2);
                Xennex.Interop.AssetResourceHandler.Attach(webView.CoreWebView2, apiBridge.Assets);
                string baseDir = AppContext.BaseDirectory;
                string wwwrootDir = Path.Combine(baseDir, "wwwroot");

                webView.CoreWebView2.SetVirtualHostNameToFolderMapping("appassets", wwwrootDir, CoreWebView2HostResourceAccessKind.Deny);
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
            var envOptions = new CoreWebView2EnvironmentOptions("--enable-usermedia-screen-capturing --autoplay-policy=no-user-gesture-required");
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
            if (!Xennex.Services.Security.LocalRequestPolicy.IsAppDocument(e.Source)) return;
            string msg;
            try { msg = e.TryGetWebMessageAsString(); } catch (ArgumentException) { return; }
            if (msg != null && msg.StartsWith("resizeWindow:") && !sidebarService.IsSidebarMode)
            {
                string dir = msg.Substring("resizeWindow:".Length).ToLowerInvariant();
                int ht = dir switch
                {
                    "left" => HTLEFT,
                    "right" => HTRIGHT,
                    "top" => HTTOP,
                    "topleft" => HTTOPLEFT,
                    "topright" => HTTOPRIGHT,
                    "bottom" => HTBOTTOM,
                    "bottomleft" => HTBOTTOMLEFT,
                    "bottomright" => HTBOTTOMRIGHT,
                    _ => 0
                };
                if (ht > 0)
                {
                    ReleaseCapture();
                    SendMessage(new WindowInteropHelper(this).Handle, WM_NCLBUTTONDOWN, ht, 0);
                    return;
                }
            }

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

        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            RestoreWindowPosition();
            StartStatusTimer();
        }
        private void RestoreWindowPosition()
        {
            if (configService.Config.WindowWidth >= 400)
            {
                this.Width = configService.Config.WindowWidth;
            }
            if (configService.Config.WindowHeight >= 300)
            {
                this.Height = configService.Config.WindowHeight;
            }

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
            try
            {
                string executable = Environment.ProcessPath;
                if (!string.IsNullOrEmpty(executable))
                    trayIcon = System.Drawing.Icon.ExtractAssociatedIcon(executable);
            }
            catch (Exception ex) { AppLog.Error("TrayIcon", ex); }
            notifyIcon = new NotifyIcon
            {
                Icon = trayIcon ?? System.Drawing.SystemIcons.Application,
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

        internal void RestoreFromTray()
        {
            this.Show();
            this.ShowInTaskbar = true;
            this.WindowState = WindowState.Normal;
            this.Visibility = Visibility.Visible;
            sidebarService.Reveal();
            this.Activate();
            this.Focus();

            var hwnd = new WindowInteropHelper(this).Handle;
            if (hwnd != IntPtr.Zero)
            {
                SetForegroundWindow(hwnd);
            }
        }

        private string PickAlicePath(string kind)
        {
            if (kind == "models")
            {
                using var folder = new FolderBrowserDialog { Description = "Pasta do encoder perceptivo instalado", UseDescriptionForTitle = true };
                return folder.ShowDialog(new DialogOwner(new WindowInteropHelper(this).Handle)) == System.Windows.Forms.DialogResult.OK ? folder.SelectedPath : "";
            }
            var filter = kind switch
            {
                "python" => "Python instalado (python.exe)|python.exe",
                "checkpoint" => "Estado da Alice (*.pt)|*.pt",
                "image" => "Imagem PNG (*.png)|*.png",
                "audio" => "Áudio WAV (*.wav)|*.wav",
                "text" => "Texto UTF-8 (*.txt)|*.txt",
                _ => null
            };
            if (filter is null) return "";
            using var dialog = new OpenFileDialog { Title = "Selecionar arquivo para a Alice", Filter = filter, CheckFileExists = true, Multiselect = false };
            return dialog.ShowDialog(new DialogOwner(new WindowInteropHelper(this).Handle)) == System.Windows.Forms.DialogResult.OK ? dialog.FileName : "";
        }

        private bool shutdownPending;
        private async void ShutdownApp()
        {
            if (shutdownPending) return;
            shutdownPending = true;
            try { if (apiBridge is not null) await apiBridge.StopAlice(); }
            catch (Exception ex) { AppLog.Error("Shutdown.Alice", ex); }
            isForceExiting = true;

            if (!sidebarService.IsSidebarMode && this.WindowState == WindowState.Normal)
            {
                configService.Config.WindowLeft = this.Left;
                configService.Config.WindowTop = this.Top;
                configService.Config.WindowWidth = this.ActualWidth > 0 ? this.ActualWidth : this.Width;
                configService.Config.WindowHeight = this.ActualHeight > 0 ? this.ActualHeight : this.Height;
                configService.SaveConfig();
            }

            StopApplicationServices();

            Application.Current.Shutdown();
        }

        private bool servicesStopped;

        private void StopApplicationServices()
        {
            if (servicesStopped) return;
            servicesStopped = true;
            Action[] cleanup = {
                () => apiBridge?.StopLocalAi(), () => apiBridge?.StopAssets(), () => sidebarService.Stop(), () => statusTimer?.Stop(),
                () => realEngineService.Stop(), () => handMotionService.Stop(),
                () => streamService?.StopNativeCapture(), () => streamService?.CloseAllViewers(),
                () => processAudioCaptureService?.StopCapture(), () => localWebServer?.Stop(),
                () => notifyIcon?.Dispose(), () => trayIcon?.Dispose()
            };
            foreach (var stop in cleanup)
            {
                try { stop(); }
                catch (Exception ex) { AppLog.Error("Shutdown", ex); }
            }
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
                StopApplicationServices();
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
