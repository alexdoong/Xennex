using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace WacomRealController
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

        public void RunBatchFile(string filename)
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, filename);
            if (!File.Exists(path))
            {
                Log("[ERR] Not found: " + filename);
                throw new FileNotFoundException("Batch file not found: " + path);
            }
            Log("[Wacom] Running " + filename + " (admin)…");
            try
            {
                var p = Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true, Verb = "runas" });
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
                throw;
            }
        }
    }
}
