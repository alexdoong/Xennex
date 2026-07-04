using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace Xennex
{
    public class WacomService
    {
        public event Action<string> OnLogReceived;
        public event Action OnStatusChanged;

        private void Log(string msg) => OnLogReceived?.Invoke(msg);

        public bool QueryWacomActive()
        {
            try
            {
                foreach (var name in new[] { "Wacom_Tablet", "Pen_Tablet", "WacomTablet" })
                    if (Process.GetProcessesByName(name).Length > 0) return true;
            }
            catch { }
            return false;
        }

        public void DisableDrivers()
        {
            string cmds = "taskkill /F /IM Wacom_Tablet.exe >nul 2>&1 & taskkill /F /IM Pen_Tablet.exe >nul 2>&1 & net stop WTabletServicePro & net start WTabletServicePro & net stop WTabletServiceCon & timeout /t 1 /nobreak >nul & net start WTabletServiceCon & taskkill /F /IM WacomDesktopCenter.exe >nul 2>&1 & timeout /t 10 /nobreak >nul & taskkill /F /IM Wacom_Tablet.exe >nul 2>&1 & taskkill /F /IM Pen_Tablet.exe >nul 2>&1";
            RunElevatedCommand(cmds, "Disabling");
        }

        public void EnableDrivers()
        {
            string cmds = "net stop WTabletServicePro & net start WTabletServicePro & net stop WTabletServiceCon & net start WTabletServiceCon & taskkill /F /IM WacomDesktopCenter.exe >nul 2>&1 & timeout /t 5 /nobreak >nul";
            RunElevatedCommand(cmds, "Enabling");
        }

        private void RunElevatedCommand(string commandArgs, string logPrefix)
        {
            Log($"[Wacom] {logPrefix} drivers (admin)…");
            try
            {
                var p = Process.Start(new ProcessStartInfo 
                { 
                    FileName = "cmd.exe", 
                    Arguments = $"/c {commandArgs}", 
                    UseShellExecute = true, 
                    Verb = "runas",
                    WindowStyle = ProcessWindowStyle.Hidden 
                });
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try { p.WaitForExit(); }
                    catch { }
                    finally
                    {
                        p.Dispose();
                        Log("[Wacom] Done.");
                        OnStatusChanged?.Invoke();
                    }
                });
            }
            catch (Exception ex)
            {
                Log("[Wacom ERR] " + ex.Message);
            }
        }
    }
}
