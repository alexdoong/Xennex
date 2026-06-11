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

        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lp);

        public const int SW_HIDE = 0;
        public const int SW_SHOW = 5;
    }
}
