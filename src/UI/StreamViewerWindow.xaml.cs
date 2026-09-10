using System.Runtime.InteropServices;
using System;
using System.IO;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Xennex.Services;

namespace Xennex.UI
{
    public partial class StreamViewerWindow : Window
    {
        private readonly string _roomId;
        private readonly string _title;
        private readonly StreamService _streamService;
        private readonly object _apiBridge;
        private bool _isPinned = false;

        public StreamViewerWindow(string roomId, string title, StreamService streamService, object apiBridge = null)
        {
            InitializeComponent();
            _roomId = roomId;
            _title = string.IsNullOrWhiteSpace(title) ? $"Stream - {roomId}" : title;
            _streamService = streamService;
            _apiBridge = apiBridge;

            TxtTitle.Text = _title;
            TxtRoomBadge.Text = roomId;
            this.Title = $"Xennex: {_title}";

            this.Loaded += StreamViewerWindow_Loaded;
        }

        private async void StreamViewerWindow_Loaded(object sender, RoutedEventArgs e)
        {
            try
            {
                if (MainWindow.SharedEnvironment != null)
                {
                    await webView.EnsureCoreWebView2Async(MainWindow.SharedEnvironment);
                }
                else
                {
                    string userFolder = Path.Combine(Path.GetTempPath(), "XennexWebView2");
                    CoreWebView2Environment env;
                    try
                    {
                        env = await CoreWebView2Environment.CreateAsync(null, userFolder);
                    }
                    catch (COMException ex) when ((uint)ex.HResult == 0x800700AA)
                    {
                        string fallbackFolder = Path.Combine(Path.GetTempPath(), $"XennexWebView2_{System.Diagnostics.Process.GetCurrentProcess().Id}");
                        env = await CoreWebView2Environment.CreateAsync(null, fallbackFolder);
                    }
                    await webView.EnsureCoreWebView2Async(env);
                }

                if (_apiBridge != null)
                {
                    webView.CoreWebView2.AddHostObjectToScript("api", _apiBridge);
                }

                webView.CoreWebView2.PermissionRequested += (s, ev) =>
                {
                    if (ev.PermissionKind == CoreWebView2PermissionKind.Camera ||
                        ev.PermissionKind == CoreWebView2PermissionKind.Microphone ||
                        (int)ev.PermissionKind == 14)
                    {
                        ev.State = CoreWebView2PermissionState.Allow;
                    }
                };

                string exePath = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName;
                string baseDir = Path.GetDirectoryName(exePath);
                string wwwrootDir = Path.Combine(baseDir, "wwwroot");

                webView.CoreWebView2.SetVirtualHostNameToFolderMapping("appassets", wwwrootDir, CoreWebView2HostResourceAccessKind.Allow);

                string safeRoom = Uri.EscapeDataString(_roomId);
                string safeTitle = Uri.EscapeDataString(_title);
                webView.CoreWebView2.Navigate($"https://appassets/index.html?mode=viewer&room={safeRoom}&title={safeTitle}");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Erro ao inicializar visualizador de transmissão: {ex.Message}", "Xennex Viewer", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private void BtnPin_Click(object sender, RoutedEventArgs e)
        {
            _isPinned = !_isPinned;
            this.Topmost = _isPinned;
            IconPin.Foreground = _isPinned ? System.Windows.Media.Brushes.Orange : new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0x94, 0xA3, 0xB8));
        }

        private void BtnMinimize_Click(object sender, RoutedEventArgs e)
        {
            this.WindowState = WindowState.Minimized;
        }

        private void BtnMaximize_Click(object sender, RoutedEventArgs e)
        {
            if (this.WindowState == WindowState.Maximized)
            {
                this.WindowState = WindowState.Normal;
                TxtMaxIcon.Text = "🗖";
            }
            else
            {
                this.WindowState = WindowState.Maximized;
                TxtMaxIcon.Text = "🗗";
            }
        }

        private void BtnClose_Click(object sender, RoutedEventArgs e)
        {
            this.Close();
        }
    }
}
