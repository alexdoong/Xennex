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

                    var window = new StreamViewerWindow(roomId, title, this);
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

        public void CloseAllViewers()
        {
            Application.Current.Dispatcher.Invoke(() =>
            {
                lock (_lock)
                {
                    foreach (var window in _viewers.Values)
                    {
                        try { window.Close(); } catch (Exception ex) { Console.WriteLine($"[StreamService] Error closing viewer window: {ex.Message}"); }
                    }
                    _viewers.Clear();
                }
            });
        }
    }
}
