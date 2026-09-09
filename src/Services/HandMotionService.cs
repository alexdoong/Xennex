using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace Xennex.Services
{
    public class HandMotionService
    {
        private Process handMotionProcess = null;
        public event Action<string> OnLogReceived;
        public event Action OnStatusChanged;

        public bool IsRunning => handMotionProcess != null && !handMotionProcess.HasExited;

        private void Log(string msg)
        {
            OnLogReceived?.Invoke(msg);
            try { string exe = Process.GetCurrentProcess().MainModule.FileName; string dir = Path.GetDirectoryName(exe); File.AppendAllText(Path.Combine(dir, "Data", "hand_motion_service.log"), DateTime.Now.ToString("s") + " - " + msg + Environment.NewLine); } catch {}
        }

        public void Start(int cameraIndex = 0)
        {
            if (handMotionProcess != null && !handMotionProcess.HasExited)
            {
                Log("[HAND MOTION] Already running.");
                return;
            }
            
            // Assuming python is installed and in PATH. The script is in the scripts folder.
            // baseDir removed
            // Depending on how it's launched, it might be in a different path.
            // Let's resolve the actual directory
            string exePath = Process.GetCurrentProcess().MainModule.FileName;
            string rootDir = Path.GetDirectoryName(exePath);
            
            // Try looking for the scripts folder
            string scriptPath = Path.Combine(rootDir, "scripts", "hand_motion.py");
            if (!File.Exists(scriptPath))
            {
                // Try looking up a few directories in case we are running from bin/Debug/...
                scriptPath = Path.GetFullPath(Path.Combine(rootDir, "..", "..", "..", "scripts", "hand_motion.py"));
                if (!File.Exists(scriptPath))
                {
                    Log("[HAND MOTION ERR] hand_motion.py not found at " + scriptPath);
                    return;
                }
            }

            // Find python executable
            string pythonExe = "python";
            string[] possiblePaths = new[]
            {
                "py",
                Environment.ExpandEnvironmentVariables(@"%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"),
                Environment.ExpandEnvironmentVariables(@"%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"),
                Environment.ExpandEnvironmentVariables(@"%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"),
                Environment.ExpandEnvironmentVariables(@"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
                "python"
            };
            
            foreach (var path in possiblePaths)
            {
                try
                {
                    var testProc = Process.Start(new ProcessStartInfo
                    {
                        FileName = path,
                        Arguments = "--version",
                        UseShellExecute = false,
                        CreateNoWindow = true
                    });
                    
                    if (testProc.WaitForExit(500))
                    {
                        pythonExe = path;
                        break;
                    }
                    else
                    {
                        try { testProc.Kill(); } catch { }
                    }
                }
                catch { }
            }

            try
            {
                handMotionProcess = new Process();
                handMotionProcess.StartInfo.FileName = pythonExe;
                handMotionProcess.StartInfo.Arguments = $"-u \"{scriptPath}\" --camera {cameraIndex}";
                handMotionProcess.StartInfo.UseShellExecute = false;
                handMotionProcess.StartInfo.CreateNoWindow = true;
                handMotionProcess.StartInfo.RedirectStandardOutput = true;
                handMotionProcess.StartInfo.RedirectStandardError = true;
                handMotionProcess.StartInfo.RedirectStandardInput = true;
                handMotionProcess.EnableRaisingEvents = true;
                
                handMotionProcess.OutputDataReceived += (s, ev) => { if (ev.Data != null) Log("[HAND MOTION] " + ev.Data); };
                handMotionProcess.ErrorDataReceived += (s, ev) => { if (ev.Data != null) Log("[HAND MOTION ERR] " + ev.Data); };
                
                handMotionProcess.Exited += (s, ev) =>
                {
                    Log("[HAND MOTION] Process ended.");
                    CleanupProcess();
                };

                handMotionProcess.Start();
                handMotionProcess.BeginOutputReadLine();
                handMotionProcess.BeginErrorReadLine();
                Log($"[HAND MOTION] Started (PID {handMotionProcess.Id}).");
                OnStatusChanged?.Invoke();
            }
            catch (Exception ex)
            {
                File.WriteAllText(Path.Combine(rootDir, "hand_motion_csharp_error.txt"), ex.ToString());
                Log("[HAND MOTION ERR] " + ex.Message);
                CleanupProcess();
            }
        }

        private void CleanupProcess()
        {
            if (handMotionProcess != null)
            {
                try { handMotionProcess.Dispose(); } catch { }
                handMotionProcess = null;
            }
            OnStatusChanged?.Invoke();
        }

        public void RecordGesture(string action)
        {
            if (IsRunning && handMotionProcess != null)
            {
                try
                {
                    handMotionProcess.StandardInput.WriteLine($"RECORD_GESTURE:{action}");
                    handMotionProcess.StandardInput.Flush();
                    Log($"[HAND MOTION] Sent RECORD_GESTURE command for {action}");
                }
                catch (Exception ex)
                {
                    Log($"[HAND MOTION ERR] Failed to send RECORD_GESTURE: {ex.Message}");
                }
            }
        }

        public void StartRecordingGesture(string action)
        {
            if (IsRunning && handMotionProcess != null)
            {
                try
                {
                    handMotionProcess.StandardInput.WriteLine($"RECORD_MOTION_START:{action}");
                    handMotionProcess.StandardInput.Flush();
                    Log($"[HAND MOTION] Sent RECORD_MOTION_START command for {action}");
                }
                catch (Exception ex)
                {
                    Log($"[HAND MOTION ERR] Failed to send RECORD_MOTION_START: {ex.Message}");
                }
            }
        }

        public void StopRecordingGesture()
        {
            if (IsRunning && handMotionProcess != null)
            {
                try
                {
                    handMotionProcess.StandardInput.WriteLine("RECORD_MOTION_STOP");
                    handMotionProcess.StandardInput.Flush();
                    Log("[HAND MOTION] Sent RECORD_MOTION_STOP command");
                }
                catch (Exception ex)
                {
                    Log($"[HAND MOTION ERR] Failed to send RECORD_MOTION_STOP: {ex.Message}");
                }
            }
        }

        public string[] GetSavedGestures()
        {
            try
            {
                string exePath = Process.GetCurrentProcess().MainModule.FileName;
                string rootDir = Path.GetDirectoryName(exePath);
                string jsonPath = Path.Combine(rootDir, "Data", "gestures.json");
                if (!File.Exists(jsonPath))
                    jsonPath = Path.GetFullPath(Path.Combine(rootDir, "..", "..", "..", "Data", "gestures.json"));
                
                if (File.Exists(jsonPath))
                {
                    var json = File.ReadAllText(jsonPath);
                    var doc = System.Text.Json.JsonDocument.Parse(json);
                    var keys = new System.Collections.Generic.List<string>();
                    foreach (var prop in doc.RootElement.EnumerateObject())
                    {
                        keys.Add(prop.Name);
                    }
                    return keys.ToArray();
                }
            }
            catch (Exception ex)
            {
                Log($"[HAND MOTION ERR] Failed to read gestures: {ex.Message}");
            }
            return new string[0];
        }

        public void DeleteGesture(string name)
        {
            try
            {
                if (IsRunning && handMotionProcess != null)
                {
                    handMotionProcess.StandardInput.WriteLine($"DELETE_GESTURE:{name}");
                    handMotionProcess.StandardInput.Flush();
                    Log($"[HAND MOTION] Sent DELETE_GESTURE command for {name}");
                }
                else
                {
                    Log("[HAND MOTION ERR] Camera must be running to delete gestures.");
                }
            }
            catch (Exception ex)
            {
                Log($"[HAND MOTION ERR] Failed to delete gesture: {ex.Message}");
            }
        }

        public string GetSwipeConfig()
        {
            try
            {
                string exePath = Process.GetCurrentProcess().MainModule.FileName;
                string rootDir = Path.GetDirectoryName(exePath);
                string jsonPath = Path.Combine(rootDir, "Data", "swipe_config.json");
                if (!File.Exists(jsonPath))
                    jsonPath = Path.GetFullPath(Path.Combine(rootDir, "..", "..", "..", "Data", "swipe_config.json"));
                
                if (File.Exists(jsonPath))
                {
                    return File.ReadAllText(jsonPath);
                }
            }
            catch (Exception ex)
            {
                Log($"[HAND MOTION ERR] Failed to read swipe config: {ex.Message}");
            }
            return "{}";
        }

        public void SaveSwipeConfig(string json)
        {
            try
            {
                string exePath = Process.GetCurrentProcess().MainModule.FileName;
                string rootDir = Path.GetDirectoryName(exePath);
                string jsonPath = Path.Combine(rootDir, "Data", "swipe_config.json");
                if (!File.Exists(jsonPath))
                {
                    string altPath = Path.GetFullPath(Path.Combine(rootDir, "..", "..", "..", "Data"));
                    if (Directory.Exists(altPath)) jsonPath = Path.Combine(altPath, "swipe_config.json");
                }
                
                File.WriteAllText(jsonPath, json);
                
                if (IsRunning && handMotionProcess != null)
                {
                    handMotionProcess.StandardInput.WriteLine("RELOAD_SWIPES");
                    handMotionProcess.StandardInput.Flush();
                    Log("[HAND MOTION] Sent RELOAD_SWIPES command");
                }
            }
            catch (Exception ex)
            {
                Log($"[HAND MOTION ERR] Failed to save swipe config: {ex.Message}");
            }
        }

        public void Stop()
        {
            if (handMotionProcess == null)
            {
                Log("[HAND MOTION] Not running.");
                return;
            }

            Log("[HAND MOTION] Sending stop signal…");
            try
            {
                if (!handMotionProcess.HasExited)
                {
                    handMotionProcess.Kill();
                    Log("[HAND MOTION] Force killed.");
                }
            }
            catch (Exception ex)
            {
                Log("[HAND MOTION ERR] " + ex.Message);
            }
            finally
            {
                CleanupProcess();
            }
        }
    }
}



