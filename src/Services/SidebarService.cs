using System;
using System.Drawing;
using System.Windows;
using System.Windows.Forms;
using System.Windows.Threading;
using Point = System.Drawing.Point;

namespace Xennex.Services
{
    public class SidebarService
    {
        private readonly Window _window;
        private readonly ConfigService _configService;
        private readonly Action<bool> _onSidebarModeChanged;

        private bool _isSidebarMode = false;
        private bool _isSlidOut = false;
        private DispatcherTimer _slideTimer;

        private double _normalLeft = 0;
        private double _normalTop = 0;
        private double _normalWidth = 800;
        private double _normalHeight = 600;

        private const double SIDEBAR_WIDTH = 320;
        private const double SIDEBAR_HEIGHT = 600;
        private const double TRIGGER_THICKNESS = 16;
        private const double SLIDE_SPEED = 30;

        public bool IsSidebarMode => _isSidebarMode;

        public SidebarService(Window window, ConfigService configService, Action<bool> onSidebarModeChanged)
        {
            _window = window;
            _configService = configService;
            _onSidebarModeChanged = onSidebarModeChanged;

            if (_configService.Config.WindowWidth >= 400) _normalWidth = _configService.Config.WindowWidth;
            if (_configService.Config.WindowHeight >= 300) _normalHeight = _configService.Config.WindowHeight;

            _slideTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(16) };
            _slideTimer.Tick += SlideTimer_Tick;
            _slideTimer.Start();
        }

        public void Stop()
        {
            _slideTimer?.Stop();
        }

        public void ToggleSidebarMode()
        {
            if (!_isSidebarMode)
            {
                SaveNormalBounds();
                EnterSidebarMode();
            }
            else
            {
                ExitSidebarMode();
            }

            _onSidebarModeChanged?.Invoke(_isSidebarMode);
        }

        private void SaveNormalBounds()
        {
            _configService.Config.WindowLeft = _window.Left;
            _configService.Config.WindowTop = _window.Top;
            _configService.Config.WindowWidth = _window.Width;
            _configService.Config.WindowHeight = _window.Height;
            _configService.SaveConfig();

            _normalLeft = _window.Left;
            _normalTop = _window.Top;
            _normalWidth = _window.Width;
            _normalHeight = _window.Height;
        }

        private void EnterSidebarMode()
        {
            _isSidebarMode = true;
            ApplySidebarDockPosition();
            _window.Topmost = true;
            _isSlidOut = true;
        }

        private void ExitSidebarMode()
        {
            _isSidebarMode = false;
            _window.Topmost = false;
            _window.Width = _normalWidth > 0 ? _normalWidth : 800;
            _window.Height = _normalHeight > 0 ? _normalHeight : 600;

            if (_configService.Config.WindowLeft >= 0 && _configService.Config.WindowTop >= 0)
            {
                _window.Left = _configService.Config.WindowLeft;
                _window.Top = _configService.Config.WindowTop;
                return;
            }

            _window.Left = (SystemParameters.WorkArea.Width - _window.Width) / 2;
            _window.Top = (SystemParameters.WorkArea.Height - _window.Height) / 2;
        }

        public void OnSidebarPositionChanged()
        {
            if (!_isSidebarMode) return;
            ApplySidebarDockPosition();
        }

        private void ApplySidebarDockPosition()
        {
            GetDpi(out double dpiX, out double dpiY);
            var scr = Screen.PrimaryScreen;
            if (scr == null) return;

            double screenLeft = scr.WorkingArea.Left / dpiX;
            double screenTop = scr.WorkingArea.Top / dpiY;
            double screenRight = scr.WorkingArea.Right / dpiX;
            double screenHeight = scr.WorkingArea.Height / dpiY;

            _window.Width = SIDEBAR_WIDTH;
            _window.Height = SIDEBAR_HEIGHT;

            string pos = _configService.Config.SidebarPosition ?? "MiddleRight";

            if (pos == "TopLeft")
            {
                _window.Top = screenTop;
                _window.Left = screenLeft - SIDEBAR_WIDTH;
            }
            else if (pos == "MiddleLeft")
            {
                _window.Top = screenTop + (screenHeight - SIDEBAR_HEIGHT) / 2;
                _window.Left = screenLeft - SIDEBAR_WIDTH;
            }
            else // MiddleRight
            {
                _window.Top = screenTop + (screenHeight - SIDEBAR_HEIGHT) / 2;
                _window.Left = screenRight;
            }

            _isSlidOut = true;
        }

        private void SlideTimer_Tick(object sender, EventArgs e)
        {
            if (!_isSidebarMode) return;

            GetDpi(out double dpiX, out double dpiY);
            var scr = Screen.PrimaryScreen;
            if (scr == null) return;

            double screenLeft = scr.WorkingArea.Left / dpiX;
            double screenTop = scr.WorkingArea.Top / dpiY;
            double screenRight = scr.WorkingArea.Right / dpiX;
            double screenHeight = scr.WorkingArea.Height / dpiY;

            CalculateDockZones(screenLeft, screenTop, screenRight, screenHeight,
                out double destShow, out double destHide, out double targetTop,
                out Rect edgeTriggerRect);

            _window.Top = targetTop;
            _window.Width = SIDEBAR_WIDTH;
            _window.Height = SIDEBAR_HEIGHT;

            Point mouseRaw = Cursor.Position;
            double mouseX = mouseRaw.X / dpiX;
            double mouseY = mouseRaw.Y / dpiY;

            bool isOverWindow = mouseX >= _window.Left && mouseX <= _window.Left + _window.Width &&
                               mouseY >= _window.Top && mouseY <= _window.Top + _window.Height;

            bool isOverTarget = mouseX >= destShow && mouseX <= destShow + SIDEBAR_WIDTH &&
                               mouseY >= targetTop && mouseY <= targetTop + SIDEBAR_HEIGHT;

            bool isOverEdge = edgeTriggerRect.Contains(mouseX, mouseY);

            bool shouldShow = isOverWindow || isOverTarget || (_isSlidOut && isOverEdge);

            if (shouldShow && _isSlidOut)
            {
                _isSlidOut = false;
            }

            double dest = shouldShow ? destShow : destHide;
            double currentPos = _window.Left;

            if (currentPos < dest)
            {
                currentPos = Math.Min(dest, currentPos + SLIDE_SPEED);
            }
            else if (currentPos > dest)
            {
                currentPos = Math.Max(dest, currentPos - SLIDE_SPEED);
            }

            _window.Left = currentPos;

            if (currentPos == destHide && !_isSlidOut && !shouldShow)
            {
                _isSlidOut = true;
            }
        }

        private void CalculateDockZones(double screenLeft, double screenTop, double screenRight, double screenHeight,
            out double destShow, out double destHide, out double targetTop, out Rect edgeTriggerRect)
        {
            string pos = _configService.Config.SidebarPosition ?? "MiddleRight";

            if (pos == "TopLeft")
            {
                destShow = screenLeft;
                destHide = screenLeft - SIDEBAR_WIDTH;
                targetTop = screenTop;
                edgeTriggerRect = new Rect(screenLeft, screenTop, TRIGGER_THICKNESS, SIDEBAR_HEIGHT);
                return;
            }

            if (pos == "MiddleLeft")
            {
                destShow = screenLeft;
                destHide = screenLeft - SIDEBAR_WIDTH;
                targetTop = screenTop + (screenHeight - SIDEBAR_HEIGHT) / 2;
                edgeTriggerRect = new Rect(screenLeft, targetTop, TRIGGER_THICKNESS, SIDEBAR_HEIGHT);
                return;
            }

            // MiddleRight (default)
            destShow = screenRight - SIDEBAR_WIDTH;
            destHide = screenRight;
            targetTop = screenTop + (screenHeight - SIDEBAR_HEIGHT) / 2;
            edgeTriggerRect = new Rect(screenRight - TRIGGER_THICKNESS, targetTop, TRIGGER_THICKNESS, SIDEBAR_HEIGHT);
        }

        private void GetDpi(out double dpiX, out double dpiY)
        {
            var dpi = System.Windows.Media.VisualTreeHelper.GetDpi(_window);
            dpiX = dpi.DpiScaleX <= 0 ? 1.0 : dpi.DpiScaleX;
            dpiY = dpi.DpiScaleY <= 0 ? 1.0 : dpi.DpiScaleY;
        }
    }
}
