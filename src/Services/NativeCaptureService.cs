using System;

namespace Xennex.Services
{
    public class NativeCaptureService
    {
        private System.Diagnostics.Process _captureWorkerProcess;
        private readonly object _workerLock = new();

        public bool StartNativeCapture(long hwnd, int pid, int fps, string resolution)
        {
            lock (_workerLock)
            {
                StopNativeCapture();

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
                string args = $"--hwnd {hwnd} --fps {fps} --res {resolution} --parentpid {currentPid} --port 59124 --quality 88";

                try
                {
                    var psi = new System.Diagnostics.ProcessStartInfo
                    {
                        FileName = exePath,
                        Arguments = args,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    };

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
                            _captureWorkerProcess.WaitForExit(1000);
                        }
                    }
                    catch (Exception ex) { AppLog.Error("CaptureWorker", ex); }
                    finally
                    {
                        _captureWorkerProcess?.Dispose();
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
                return _captureWorkerProcess != null && !_captureWorkerProcess.HasExited;
            }
        }

    }
}
