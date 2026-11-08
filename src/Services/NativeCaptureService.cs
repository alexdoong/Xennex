using System;
using System.Runtime.InteropServices;
using System.Linq;
using System.Text.Json;
using System.Windows.Forms;
using Xennex.Services.Security;

namespace Xennex.Services
{
    public class NativeCaptureService
    {
        private System.Diagnostics.Process _captureWorkerProcess;
        private readonly object _workerLock = new();
        [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr hwnd);
        [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hwnd);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);

        public string GetCaptureMonitors() => JsonSerializer.Serialize(Screen.AllScreens.Select(screen => new
        { Id = screen.DeviceName, Width = screen.Bounds.Width, Height = screen.Bounds.Height, Primary = screen.Primary }));

        public bool StartNativeCapture(long hwnd, int pid, int fps, string resolution) => StartWorker(hwnd, fps, resolution, null);
        public bool StartGameCapture(long hwnd, int pid, int fps, string resolution)
        {
            try
            {
                GetWindowThreadProcessId(new IntPtr(hwnd), out uint actual);
                if (pid <= 0 || actual != pid) return false;
                using var game = System.Diagnostics.Process.GetProcessById(pid);
                return StartWorker(hwnd, fps, resolution, null, pid, game.StartTime.ToUniversalTime().Ticks);
            }
            catch (Exception ex) { AppLog.Error("CaptureWorker.Game", ex); return false; }
        }

        public bool StartDesktopCapture(string display, int fps, string resolution)
        {
            try
            {
                if (!Screen.AllScreens.Any(screen => string.Equals(screen.DeviceName, display, StringComparison.OrdinalIgnoreCase))) return false;
                return StartWorker(0, fps, resolution, display);
            }
            catch (Exception ex) { AppLog.Error("CaptureWorker.Display", ex); return false; }
        }

        private bool StartWorker(long hwnd, int fps, string resolution, string display, int gamePid = 0, long gameStart = 0)
        {
            lock (_workerLock)
            {
                try { StopNativeCapture(); }
                catch (Exception ex) { AppLog.Error("CaptureWorker.StopPrevious", ex); return false; }
                if (hwnd != 0 && (!IsWindow(new IntPtr(hwnd)) || IsIconic(new IntPtr(hwnd)))) return false;
                if (hwnd < 0 || resolution is not ("source" or "480p" or "720p" or "1080p" or "1440p" or "2160p")) return false;
                fps = fps <= 0 ? 120 : Math.Clamp(fps, 1, 120);

                string exeName = "Xennex.CaptureWorker.exe";
                string baseDir = AppContext.BaseDirectory;
                string exePath = System.IO.Path.Combine(baseDir, exeName);

                if (!System.IO.File.Exists(exePath))
                {
                    string devPath = System.IO.Path.Combine(baseDir, "..", "..", "..", "src", "CaptureWorker", "bin", "Release", "net8.0-windows10.0.19041.0", exeName);
                    if (System.IO.File.Exists(devPath))
                    {
                        exePath = System.IO.Path.GetFullPath(devPath);
                    }
                }

                if (!System.IO.File.Exists(exePath))
                {
                    Console.WriteLine($"[StreamService] Xennex.CaptureWorker.exe não encontrado em: {exePath}");
                    return false;
                }

                int currentPid = System.Diagnostics.Process.GetCurrentProcess().Id;
                try
                {
                    var psi = new System.Diagnostics.ProcessStartInfo
                    {
                        FileName = exePath,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    };
                    foreach (string argument in new[] { "--hwnd", hwnd.ToString(), "--fps", fps.ToString(), "--res", resolution,
                        "--parentpid", currentPid.ToString(), "--port", "59124", "--quality", "88", "--token", LocalRequestPolicy.CaptureToken })
                        psi.ArgumentList.Add(argument);
                    if (display != null)
                    {
                        psi.ArgumentList.Add("--backend"); psi.ArgumentList.Add("dxgi");
                        psi.ArgumentList.Add("--display"); psi.ArgumentList.Add(display);
                    }
                    if (gamePid > 0)
                    {
                        foreach (string argument in new[] { "--backend", "game", "--gamepid", gamePid.ToString(), "--gamestart", gameStart.ToString() }) psi.ArgumentList.Add(argument);
                    }

                    _captureWorkerProcess = System.Diagnostics.Process.Start(psi);
                    if (_captureWorkerProcess != null)
                    {
                        Console.WriteLine($"[StreamService] CaptureWorker iniciado com sucesso (PID: {_captureWorkerProcess.Id}) para HWND: 0x{hwnd:X}");
                        return true;
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[StreamService] Erro ao iniciar CaptureWorker: {ex.Message}");
                }

                return false;
            }
        }

        public void StopNativeCapture()
        {
            lock (_workerLock)
            {
                if (_captureWorkerProcess != null)
                {
                    try
                    {
                        if (!_captureWorkerProcess.HasExited)
                        {
                            _captureWorkerProcess.Kill();
                            if (!_captureWorkerProcess.WaitForExit(3000))
                                throw new InvalidOperationException("O processo de captura anterior ainda está encerrando.");
                        }
                    }
                    catch (Exception ex) { AppLog.Error("CaptureWorker", ex); throw; }
                    if (_captureWorkerProcess.HasExited)
                    {
                        _captureWorkerProcess.Dispose();
                        _captureWorkerProcess = null;
                        Console.WriteLine("[StreamService] CaptureWorker finalizado e recursos liberados.");
                    }
                }
            }
        }

        public bool IsNativeCaptureRunning()
        {
            lock (_workerLock)
            {
                try { return _captureWorkerProcess != null && !_captureWorkerProcess.HasExited; }
                catch (InvalidOperationException) { return false; }
            }
        }

    }
}
