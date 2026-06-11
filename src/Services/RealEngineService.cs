using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace WacomRealController
{
    public class RealEngineService
    {
        private Process realProcess = null;
        private IntPtr consoleWindowHandle = IntPtr.Zero;
        private bool isConsoleVisible = false;

        public event Action<string> OnLogReceived;
        public event Action OnStatusChanged;
        public event Action<bool> OnConsoleAvailable; // true: available and hidden, false: not available

        public bool IsRunning => realProcess != null && !realProcess.HasExited;
        public bool IsConsoleVisible => isConsoleVisible;
        public bool CanToggleConsole => consoleWindowHandle != IntPtr.Zero;

        private void Log(string msg) => OnLogReceived?.Invoke(msg);

        public void Start(string realExePath)
        {
            if (realProcess != null && !realProcess.HasExited)
            {
                Log("[REAL] Already running.");
                return;
            }
            if (!File.Exists(realExePath))
            {
                Log("[REAL ERR] Path not set.");
                throw new FileNotFoundException("REAL.exe path not set or file not found.");
            }
            try
            {
                realProcess = new Process();
                realProcess.StartInfo.FileName               = realExePath;
                realProcess.StartInfo.UseShellExecute        = false;
                realProcess.StartInfo.CreateNoWindow         = true;
                realProcess.StartInfo.RedirectStandardOutput = true;
                realProcess.StartInfo.RedirectStandardError  = true;
                realProcess.StartInfo.RedirectStandardInput  = true;
                realProcess.EnableRaisingEvents              = true;
                realProcess.OutputDataReceived += (s, ev) => { if (ev.Data != null) Log(ev.Data); };
                realProcess.ErrorDataReceived  += (s, ev) => { if (ev.Data != null) Log("[ERR] " + ev.Data); };
                realProcess.Exited += (s, ev) =>
                {
                    Log("[REAL] Process ended.");
                    if (realProcess != null)
                    {
                        realProcess.Dispose();
                        realProcess = null;
                    }
                    consoleWindowHandle = IntPtr.Zero;
                    isConsoleVisible = false;
                    OnStatusChanged?.Invoke();
                    OnConsoleAvailable?.Invoke(false);
                };

                realProcess.Start();
                realProcess.BeginOutputReadLine();
                realProcess.BeginErrorReadLine();
                int pid = realProcess.Id;
                Log(string.Format("[REAL] Started (PID {0}).", pid));
                OnStatusChanged?.Invoke();

                // Find and hide the AllocConsole window
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    IntPtr hwnd = IntPtr.Zero;
                    for (int i = 0; i < 30 && hwnd == IntPtr.Zero; i++)
                    {
                        Thread.Sleep(100);
                        hwnd = FindConsoleWindow(pid);
                    }
                    if (hwnd != IntPtr.Zero)
                    {
                        consoleWindowHandle = hwnd;
                        Win32.ShowWindow(hwnd, Win32.SW_HIDE);
                        isConsoleVisible = false;
                        Log("[REAL] Console window hidden automatically.");
                        OnConsoleAvailable?.Invoke(true);
                    }
                });
            }
            catch (Exception ex)
            {
                Log("[REAL ERR] " + ex.Message);
                if (realProcess != null)
                {
                    realProcess.Dispose();
                    realProcess = null;
                }
                throw;
            }
        }

        public void Stop()
        {
            if (realProcess == null || realProcess.HasExited)
            {
                Log("[REAL] Not running.");
                return;
            }
            Log("[REAL] Sending stop signal…");
            try
            {
                realProcess.StandardInput.WriteLine();
                realProcess.StandardInput.Flush();
                if (!realProcess.WaitForExit(2000))
                {
                    realProcess.Kill();
                    Log("[REAL] Force killed.");
                }
            }
            catch (Exception ex)
            {
                Log("[REAL ERR] " + ex.Message);
                try { realProcess.Kill(); } catch { }
            }
        }

        public void ToggleConsoleWindow()
        {
            if (consoleWindowHandle == IntPtr.Zero) return;
            if (isConsoleVisible)
            {
                Win32.ShowWindow(consoleWindowHandle, Win32.SW_HIDE);
                isConsoleVisible = false;
            }
            else
            {
                Win32.ShowWindow(consoleWindowHandle, Win32.SW_SHOW);
                isConsoleVisible = true;
            }
        }

        private IntPtr FindConsoleWindow(int pid)
        {
            IntPtr found = IntPtr.Zero;
            Win32.EnumWindows((hWnd, _) =>
            {
                uint wpid;
                Win32.GetWindowThreadProcessId(hWnd, out wpid);
                if (wpid == (uint)pid)
                {
                    var sb = new StringBuilder(256);
                    Win32.GetClassName(hWnd, sb, sb.Capacity);
                    if (sb.ToString() == "ConsoleWindowClass")
                    {
                        found = hWnd;
                        return false;
                    }
                }
                return true;
            }, IntPtr.Zero);
            return found;
        }
    }
}
