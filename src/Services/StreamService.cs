using System;
using System.Collections.Generic;
using System.Windows;
using Xennex.UI;

namespace Xennex.Services
{
    public class StreamService
    {
        private readonly Dictionary<string, StreamViewerWindow> _viewers = new();
        private readonly object _lock = new();
        public object ApiBridge { get; set; }

        public bool OpenViewer(string roomId, string title)
        {
            if (string.IsNullOrWhiteSpace(roomId)) return false;

            Application.Current.Dispatcher.Invoke(() =>
            {
                lock (_lock)
                {
                    if (_viewers.TryGetValue(roomId, out var existingWindow))
                    {
                        if (existingWindow.WindowState == WindowState.Minimized)
                        {
                            existingWindow.WindowState = WindowState.Normal;
                        }
                        existingWindow.Activate();
                        existingWindow.Focus();
                        return;
                    }

                    var window = new StreamViewerWindow(roomId, title, this, ApiBridge);
                    window.Closed += (s, e) =>
                    {
                        lock (_lock)
                        {
                            _viewers.Remove(roomId);
                        }
                    };

                    _viewers[roomId] = window;
                    window.Show();
                }
            });

            return true;
        }

        public bool CloseViewer(string roomId)
        {
            if (string.IsNullOrWhiteSpace(roomId)) return false;

            return Application.Current.Dispatcher.Invoke(() =>
            {
                lock (_lock)
                {
                    if (_viewers.TryGetValue(roomId, out var window))
                    {
                        window.Close();
                        _viewers.Remove(roomId);
                        return true;
                    }
                    return false;
                }
            });
        }

        public bool SetAlwaysOnTop(string roomId, bool alwaysOnTop)
        {
            if (string.IsNullOrWhiteSpace(roomId)) return false;

            return Application.Current.Dispatcher.Invoke(() =>
            {
                lock (_lock)
                {
                    if (_viewers.TryGetValue(roomId, out var window))
                    {
                        window.Topmost = alwaysOnTop;
                        return true;
                    }
                    return false;
                }
            });
        }


        private readonly NativeCaptureService _nativeCapture = new();

        public bool StartNativeCapture(long hwnd, int pid, int fps, string resolution) =>
            _nativeCapture.StartNativeCapture(hwnd, pid, fps, resolution);
        public void StopNativeCapture() => _nativeCapture.StopNativeCapture();
        public bool IsNativeCaptureRunning() => _nativeCapture.IsNativeCaptureRunning();

        public void CloseAllViewers()
        {
            Application.Current.Dispatcher.Invoke(() =>
            {
                lock (_lock)
                {
                    foreach (var window in new List<StreamViewerWindow>(_viewers.Values))
                    {
                        try { window.Close(); } catch (Exception ex) { Console.WriteLine($"[StreamService] Error closing viewer window: {ex.Message}"); }
                    }
                    _viewers.Clear();
                }
            });
        }
    }
}
