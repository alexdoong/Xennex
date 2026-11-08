using System;
using System.Windows;
using Xennex.UI;
using Xennex.Services;

namespace Xennex
{
    public class Program
    {
        [STAThread]
        public static void Main()
        {
            try
            {
                using var instance = new SingleInstanceCoordinator();
                if (!instance.IsPrimary)
                {
                    instance.SignalPrimary();
                    return;
                }

                var app = new Application();
                app.DispatcherUnhandledException += (s, ev) => {
                    AppLog.Error("UI", ev.Exception);
                    ev.Handled = true;
                };
                AppDomain.CurrentDomain.UnhandledException += (s, ev) => {
                    AppLog.Error("Unhandled", ev.ExceptionObject as Exception);
                };
                var window = new MainWindow();
                window.Loaded += (s, e) => instance.StartListening(window.Dispatcher, window.RestoreFromTray);
                app.Run(window);
            }
            catch (Exception ex)
            {
                AppLog.Error("Startup", ex);
                MessageBox.Show($"Erro fatal ao iniciar Xennex: {ex.Message}", "Xennex", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
    }
}
