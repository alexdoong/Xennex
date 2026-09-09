using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows;
using Xennex.UI;

namespace Xennex
{
    public class Program
    {
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        private static extern int RegisterWindowMessage(string lpString);

        [DllImport("user32.dll")]
        private static extern bool PostMessage(IntPtr hWnd, int Msg, IntPtr wParam, IntPtr lParam);

        private const int HWND_BROADCAST = 0xffff;

        [STAThread]
        public static void Main()
        {
            try
            {
                Process current = Process.GetCurrentProcess();
                Process[] processes = Process.GetProcessesByName(current.ProcessName);

                if (processes.Length > 1)
                {
                    int msg = RegisterWindowMessage("XENNEX_RESTORE_INSTANCE_MSG");
                    PostMessage((IntPtr)HWND_BROADCAST, msg, IntPtr.Zero, IntPtr.Zero);
                    return;
                }

                var app = new Application();
                app.DispatcherUnhandledException += (s, ev) => {
                    ev.Handled = true;
                };
                AppDomain.CurrentDomain.UnhandledException += (s, ev) => {
                };
                app.Run(new MainWindow());
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Erro fatal ao iniciar Xennex: {ex.Message}", "Xennex", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
    }
}
