using System;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Forms;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using Point = System.Drawing.Point;
using Rectangle = System.Drawing.Rectangle;

namespace Xennex.Services
{
    public class SidebarService
    {
        private readonly Window _window;
        private readonly ConfigService _configService;
        private readonly Action<bool> _onSidebarModeChanged;
        private readonly DispatcherTimer _slideTimer;
        private readonly Stopwatch _clock = Stopwatch.StartNew();
        private Rect _normalBounds;
        private NativeRect _normalPixels;
        private WindowState _normalState;
        private double _normalMinWidth, _normalMinHeight;
        private bool _normalTopmost;
        private string _screenName;
        private Rectangle _workArea;
        private long _lastInside, _lastScreenCheck;
        private readonly CompactMotion _motion = new();
        private readonly CompactFrameCadence _cadence = new();
        private bool _rendering;
        private TimeSpan _lastRenderingTime = TimeSpan.MinValue;
        private CompactDockGeometry _dock;
        private int _fullWidth, _fullHeight;
        private bool _isSidebarMode;
        private bool _pinned;
        private bool _isInteracting;

        public Action<int, int, string> OnGeometryChanged;
        public Func<Point> CursorProvider { get; set; } = () => System.Windows.Forms.Cursor.Position;
        private IntPtr Handle => new WindowInteropHelper(_window).Handle;
        public bool IsSidebarMode => _isSidebarMode;
        public bool IsPinned => _pinned;

        public SidebarService(Window window, ConfigService configService, Action<bool> onSidebarModeChanged)
        {
            _window = window;
            _configService = configService;
            _onSidebarModeChanged = onSidebarModeChanged;
            // This timer only detects hover/idle changes. It never clocks an active animation.
            _slideTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(50) };
            _slideTimer.Tick += (_, _) => { if (!_rendering) UpdateAnimation(); };
            _window.Deactivated += (_, _) => { _isInteracting = false; _lastInside = _clock.ElapsedMilliseconds; };
        }

        public void Stop()
        {
            _slideTimer.Stop();
            StopRendering();
        }

        private void StartRendering()
        {
            if (_rendering) return;
            _rendering = true;
            _cadence.Reset();
            _lastRenderingTime = TimeSpan.MinValue;
            CompositionTarget.Rendering += RenderFrame;
        }

        private void StopRendering()
        {
            if (!_rendering) return;
            CompositionTarget.Rendering -= RenderFrame;
            _rendering = false;
        }

        private void RenderFrame(object sender, EventArgs e)
        {
            // WPF may raise Rendering twice with the same timestamp after layout.
            if (e is RenderingEventArgs frame)
            {
                if (frame.RenderingTime == _lastRenderingTime) return;
                _lastRenderingTime = frame.RenderingTime;
            }
            if (!_cadence.ShouldRender(_clock.Elapsed.TotalMilliseconds, _configService.Config.SidebarAnimationFps)) return;
            UpdateAnimation();
        }

        public void ToggleSidebarMode()
        {
            if (_isSidebarMode) ExitSidebarMode();
            else EnterSidebarMode();
            _onSidebarModeChanged?.Invoke(_isSidebarMode);
        }

        private void EnterSidebarMode()
        {
            _normalState = _window.WindowState;
            _normalBounds = _normalState == WindowState.Normal
                ? new Rect(_window.Left, _window.Top, _window.ActualWidth, _window.ActualHeight)
                : _window.RestoreBounds;
            GetWindowRect(Handle, out _normalPixels);
            _normalMinWidth = _window.MinWidth;
            _normalMinHeight = _window.MinHeight;
            _normalTopmost = _window.Topmost;
            _screenName = Screen.FromHandle(Handle).DeviceName;
            _configService.Config.WindowLeft = _normalBounds.Left;
            _configService.Config.WindowTop = _normalBounds.Top;
            _configService.Config.WindowWidth = _normalBounds.Width;
            _configService.Config.WindowHeight = _normalBounds.Height;
            _configService.SaveConfig();

            _isSidebarMode = true;
            _pinned = false;
            _isInteracting = false;
            _window.WindowState = WindowState.Normal;
            // WPF otherwise coerces Width=360 to the desktop MinWidth=600.
            _window.MinWidth = 0;
            _window.MinHeight = 0;
            _window.Topmost = true;
            Reveal();
            _slideTimer.Start();
        }

        private void ExitSidebarMode()
        {
            Stop();
            _isInteracting = false;
            _window.MinWidth = _normalMinWidth;
            _window.MinHeight = _normalMinHeight;
            _window.Width = _normalBounds.Width;
            _window.Height = _normalBounds.Height;
            _window.Left = _normalBounds.Left;
            _window.Top = _normalBounds.Top;
            // Physical coordinates avoid mixed-DPI and negative-origin translation errors.
            if (_normalState == WindowState.Normal)
            {
                var screen = Screen.FromRectangle(new Rectangle(_normalPixels.Left, _normalPixels.Top,
                    _normalPixels.Right - _normalPixels.Left, _normalPixels.Bottom - _normalPixels.Top));
                int left = Math.Clamp(_normalPixels.Left, screen.WorkingArea.Left,
                    Math.Max(screen.WorkingArea.Left, screen.WorkingArea.Right - (_normalPixels.Right - _normalPixels.Left)));
                int top = Math.Clamp(_normalPixels.Top, screen.WorkingArea.Top,
                    Math.Max(screen.WorkingArea.Top, screen.WorkingArea.Bottom - (_normalPixels.Bottom - _normalPixels.Top)));
                SetWindowPos(Handle, IntPtr.Zero, left, top, 0, 0, 0x0015);
            }
            _window.Topmost = _normalTopmost;
            _window.WindowState = _normalState;
            _isSidebarMode = false;
            _pinned = false;
        }

        public void SetPinned(bool value)
        {
            _pinned = value && _isSidebarMode;
            if (_pinned) Reveal();
            else _lastInside = _clock.ElapsedMilliseconds;
        }

        public void SetInteracting(bool interacting)
        {
            _isInteracting = interacting && _isSidebarMode;
            _lastInside = _clock.ElapsedMilliseconds;
        }

        public void SetPlacement(int inset, int verticalPercent)
        {
            if (inset < 0 || inset > 2000 || verticalPercent < -1 || verticalPercent > 100)
                throw new ArgumentOutOfRangeException(nameof(inset), "Posição fora dos limites.");
            _configService.Config.SidebarInset = inset;
            _configService.Config.SidebarVerticalPercent = verticalPercent;
            _configService.SaveConfig();
            OnSidebarPositionChanged();
        }

        public void OnSidebarPositionChanged()
        {
            if (_isSidebarMode) Reveal();
        }

        public void Reveal()
        {
            if (!_isSidebarMode) return;
            _workArea = CurrentScreen().WorkingArea;
            var dpi = VisualTreeHelper.GetDpi(_window);
            _fullWidth = Math.Min((int)Math.Round(360 * dpi.DpiScaleX), _workArea.Width);
            _fullHeight = Math.Min((int)Math.Round(680 * dpi.DpiScaleY), _workArea.Height);
            var dock = _dock = Geometry();
            StopRendering();
            _motion.Reset(_clock.ElapsedMilliseconds);
            var rect = dock.ShownRect;
            SetWindowPos(Handle, IntPtr.Zero, rect.X, rect.Y, rect.Width, rect.Height, 0x0014);

            int openWidthDIPs = (int)Math.Round(_fullWidth / dpi.DpiScaleX);
            int openHeightDIPs = (int)Math.Round(_fullHeight / dpi.DpiScaleY);
            OnGeometryChanged?.Invoke(openWidthDIPs, openHeightDIPs, dock.EffectiveCollapseEdge);

            // Do not disappear under the pointer during the mode transition.
            _lastInside = _clock.ElapsedMilliseconds + 900;
            _lastScreenCheck = _clock.ElapsedMilliseconds;
        }

        private Screen CurrentScreen() =>
            Screen.AllScreens.FirstOrDefault(s => s.DeviceName == _screenName) ?? Screen.PrimaryScreen;

        private CompactDockGeometry Geometry()
        {
            var dpi = VisualTreeHelper.GetDpi(_window);
            return CompactDockGeometry.CalculateDpi(
                _workArea,
                _fullWidth,
                _fullHeight,
                _configService.Config.SidebarPosition,
                dpi.DpiScaleX,
                dpi.DpiScaleY,
                _configService.Config.SidebarInset,
                _configService.Config.SidebarVerticalPercent,
                _configService.Config.SidebarCollapseEdge);
        }

        private void UpdateAnimation()
        {
            if (!_isSidebarMode || !_window.IsVisible || _window.WindowState == WindowState.Minimized)
            {
                StopRendering();
                return;
            }
            long now = _clock.ElapsedMilliseconds;
            if (now - _lastScreenCheck > 250)
            {
                _lastScreenCheck = now;
                if (CurrentScreen().WorkingArea != _workArea) { Reveal(); return; }
            }
            if (!GetWindowRect(Handle, out var native)) return;
            var dock = _dock;
            var mouse = CursorProvider?.Invoke() ?? System.Windows.Forms.Cursor.Position;
            var currentRect = new Rectangle(native.Left, native.Top, native.Right - native.Left, native.Bottom - native.Top);
            var visible = Rectangle.Intersect(_workArea, currentRect);
            // Keep the trigger stable while the panel travels from an offset position.
            // Never inflate it across a shared monitor boundary.
            bool over = visible.Contains(mouse) || dock.HiddenRect.Contains(mouse);
            // A press that began in the panel or active input keeps it open.
            bool interacting = _isInteracting || (Control.MouseButtons != MouseButtons.None && now - _lastInside < 550);
            if (over || interacting) _lastInside = now;
            bool show = _pinned || over || interacting || now - _lastInside < 650;
            var progress = _motion.Update(show, now, SystemParameters.ClientAreaAnimation);
            var nextRect = dock.GetInterpolatedRect(progress);
            if (currentRect != nextRect)
            {
                SetWindowPos(Handle, IntPtr.Zero, nextRect.X, nextRect.Y, nextRect.Width, nextRect.Height, 0x0014);
            }
            if (_motion.IsMoving(now)) StartRendering();
            else StopRendering();
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct NativeRect { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);
        [DllImport("user32.dll")] private static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    }
}
