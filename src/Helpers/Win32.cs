using System;
using System.Runtime.InteropServices;
using System.Text;

namespace WacomRealController
{
    public static class Win32
    {
        [DllImport("user32.dll")]
        public static extern bool DestroyIcon(IntPtr h);

        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int n);

        [DllImport("user32.dll")]
        public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);

        [DllImport("user32.dll")]
        public static extern bool EnumWindows(EnumWindowsProc fn, IntPtr lp);

        [DllImport("user32.dll", SetLastError = true)]
        public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int n);

        [DllImport("user32.dll")]
        public static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll")]
        public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

        [DllImport("user32.dll")]
        public static extern IntPtr GetShellWindow();

        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lp);

        public const int SW_HIDE = 0;
        public const int SW_SHOW = 5;

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        public static bool IsForegroundWindowFullScreen()
        {
            IntPtr fg = GetForegroundWindow();
            if (fg == IntPtr.Zero) return false;

            IntPtr shell = GetShellWindow();
            if (fg == shell) return false;

            StringBuilder sb = new StringBuilder(256);
            GetClassName(fg, sb, sb.Capacity);
            string cls = sb.ToString();
            if (cls == "Progman" || cls == "WorkerW") return false;

            RECT rect;
            if (GetWindowRect(fg, out rect))
            {
                int w = rect.Right - rect.Left;
                int h = rect.Bottom - rect.Top;
                try
                {
                    var scr = System.Windows.Forms.Screen.FromHandle(fg);
                    if (w >= scr.Bounds.Width && h >= scr.Bounds.Height)
                    {
                        return true;
                    }
                }
                catch { }
            }
            return false;
        }
    }
}
