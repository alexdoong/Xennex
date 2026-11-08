using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Xennex.Services.Gestures;

namespace Xennex.Services
{
    /// <summary>Supervises the camera worker. Only validated profiles and JSON commands cross the boundary.</summary>
    public class HandMotionService
    {
        private readonly object sync = new();
        private readonly GestureProfileStore profiles = new(Path.Combine(AppContext.BaseDirectory, "Data"));
        private Process process;
        private string recordingId;
        private string recordingToken;
        private int revision;
        private JsonObject state = new() { ["message"] = "Câmera desligada.", ["armed"] = false };
        public event Action<string> OnLogReceived;
        public event Action OnStatusChanged;
        public bool IsRunning { get { lock (sync) return Running(); } }
        private bool Running() => process != null && !process.HasExited;

        public string GetConfig() => profiles.Read().ToJsonString();
        public string GetStatus()
        {
            lock (sync)
            {
                var snapshot = (JsonObject)state.DeepClone();
                snapshot["running"] = Running();
                if (!Running()) { snapshot["armed"] = false; snapshot["recording"] = false; snapshot["points"] = null; }
                snapshot["revision"] = revision;
                return snapshot.ToJsonString();
            }
        }
        public void SaveConfig(string json)
        {
            lock (sync)
            {
                PauseForChange();
                profiles.Save(json);
                revision++;
                Send(new { type = "reload" });
                state["message"] = "Configuração salva. Controle pausado.";
            }
        }
        public void ClearSamples(string id)
        {
            lock (sync)
            {
                PauseForChange();
                profiles.ClearSamples(id);
                revision++;
                Send(new { type = "reload" });
            }
        }
        private void PauseForChange()
        {
            recordingId = null;
            recordingToken = null;
            state["armed"] = false;
            state["recording"] = false;
            Send(new { type = "arm", enabled = false });
            Send(new { type = "cancel" });
        }
        public void SetControl(bool enabled)
        {
            lock (sync)
            {
                if (!Running()) throw new InvalidOperationException("Inicie a câmera primeiro.");
                if (recordingId != null && enabled) throw new InvalidOperationException("Aguarde a gravação.");
                Send(new { type = "arm", enabled });
            }
        }
        public void RecordSample(string id)
        {
            lock (sync)
            {
                if (!Running()) throw new InvalidOperationException("Inicie a câmera primeiro.");
                var gesture = profiles.Read()["gestures"].AsArray().FirstOrDefault(g => (string)g["id"] == id);
                if (gesture == null || (string)gesture["source"] is not ("pose" or "motion"))
                    throw new InvalidOperationException("Escolha uma pose ou movimento personalizado.");
                if (gesture["samples"].AsArray().Count >= 8) throw new InvalidOperationException("Limite de oito amostras.");
                recordingId = id;
                recordingToken = Guid.NewGuid().ToString("N");
                state["armed"] = false;
                state["recording"] = true;
                state["stage"] = "countdown";
                state["remaining"] = 3;
                Send(new { type = "record", id, token = recordingToken });
            }
        }
        public void CancelRecording()
        {
            lock (sync)
            {
                recordingId = null;
                recordingToken = null;
                state["recording"] = false;
                Send(new { type = "cancel" });
            }
        }
        private void Send(object command)
        {
            if (!Running()) return;
            try
            {
                process.StandardInput.WriteLine(JsonSerializer.Serialize(command));
                process.StandardInput.Flush();
            }
            catch (Exception error) when (error is IOException or InvalidOperationException)
            {
                state["armed"] = false;
                state["message"] = "A comunicação com Gestures foi interrompida. Reinicie a câmera.";
                AppLog.Error("Gestures.Send", error);
                throw new InvalidOperationException((string)state["message"], error);
            }
        }
        public void Start(int cameraIndex = 0)
        {
            lock (sync)
            {
                if (Running()) return;
                try
                {
                    profiles.Read();
                    string root = AppContext.BaseDirectory;
                    string script = Path.Combine(root, "scripts", "hand_motion.py");
                    if (!File.Exists(script)) throw new FileNotFoundException("Scripts de Gestures ausentes. Recompile o aplicativo.");
                    // An isolated environment avoids incompatible global OpenCV/MediaPipe installations.
                    string python = Environment.GetEnvironmentVariable("XENNEX_GESTURE_PYTHON");
                    if (string.IsNullOrWhiteSpace(python)) python = Path.Combine(root, ".venv", "Scripts", "python.exe");
                    string bundled = Path.Combine(root, "scripts", "Xennex.GesturesWorker.exe");
                    bool useBundle = File.Exists(bundled) && string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("XENNEX_GESTURE_PYTHON"));
                    if (!useBundle && !File.Exists(python))
                        throw new FileNotFoundException("Prepare Gestures executando scripts/setup_gestures.ps1 na pasta do app (Python 3.11).");
                    process?.Dispose();
                    var worker = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = useBundle ? bundled : python, WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
                        },
                        EnableRaisingEvents = true
                    };
                    if (!useBundle) { worker.StartInfo.ArgumentList.Add("-u"); worker.StartInfo.ArgumentList.Add(script); }
                    foreach (string argument in new[] { "--camera", Math.Max(0, cameraIndex).ToString(), "--config", profiles.FilePath })
                        worker.StartInfo.ArgumentList.Add(argument);
                    worker.OutputDataReceived += (_, e) => Receive(worker, e.Data);
                    worker.ErrorDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) OnLogReceived?.Invoke("[Gestures] " + e.Data); };
                    worker.Exited += (_, _) =>
                    {
                        lock (sync)
                        {
                            if (process != worker) return;
                            state["armed"] = false;
                            state["recording"] = false;
                            state["points"] = null;
                            recordingId = null;
                            recordingToken = null;
                        }
                        OnStatusChanged?.Invoke();
                    };
                    state = new JsonObject { ["message"] = "Iniciando câmera…", ["armed"] = false, ["recording"] = false };
                    process = worker;
                    worker.Start();
                    worker.BeginOutputReadLine();
                    worker.BeginErrorReadLine();
                }
                catch (Exception error)
                {
                    process?.Dispose();
                    process = null;
                    state["message"] = error.Message;
                    state["armed"] = false;
                    AppLog.Error("Gestures.Start", error);
                }
            }
            OnStatusChanged?.Invoke();
        }
        private void Receive(Process worker, string line)
        {
            if (string.IsNullOrWhiteSpace(line)) return;
            lock (sync)
            {
                if (process != worker) return;
                try
                {
                    var message = JsonNode.Parse(line);
                    switch ((string)message?["type"])
                    {
                        case "frame":
                            foreach (string key in new[] { "points", "hand", "armed", "match", "recording", "metrics" })
                                state[key] = message[key]?.DeepClone();
                            break;
                        case "status":
                            state["message"] = message["message"]?.DeepClone();
                            state["armed"] = message["armed"]?.DeepClone();
                            break;
                        case "recording":
                            state["stage"] = message["stage"]?.DeepClone();
                            state["remaining"] = message["remaining"]?.DeepClone();
                            break;
                        case "recorded":
                            if ((string)message["id"] != recordingId || (string)message["token"] != recordingToken) break;
                            profiles.AddSample(recordingId, message["sample"]);
                            recordingId = null;
                            recordingToken = null;
                            revision++;
                            state["recording"] = false;
                            state["message"] = "Amostra salva. Repita em posições semelhantes para melhorar o reconhecimento.";
                            Send(new { type = "reload" });
                            break;
                        case "recognized":
                            state["match"] = message["name"]?.DeepClone();
                            state["executed"] = message["executed"]?.DeepClone();
                            break;
                        case "error":
                            recordingId = null;
                            recordingToken = null;
                            state["recording"] = false;
                            state["armed"] = false;
                            state["message"] = message["message"]?.DeepClone();
                            OnLogReceived?.Invoke("[Gestures] " + (string)message["message"]);
                            break;
                        case "stopped":
                            state["armed"] = false;
                            state["recording"] = false;
                            state["points"] = null;
                            break;
                    }
                }
                catch (Exception error)
                {
                    recordingId = null;
                    recordingToken = null;
                    state["recording"] = false;
                    state["armed"] = false;
                    state["message"] = error.Message;
                    try { Send(new { type = "arm", enabled = false }); } catch (InvalidOperationException) { }
                    AppLog.Error("Gestures.WorkerMessage", error);
                }
            }
        }
        public void Stop()
        {
            Process worker;
            lock (sync)
            {
                worker = process;
                if (!Running()) return;
                recordingId = null;
                recordingToken = null;
                try { Send(new { type = "stop" }); } catch (InvalidOperationException) { }
            }
            // Worker watchdog releases input even if a camera read blocks. Allow it to run before termination.
            try { if (!worker.WaitForExit(2000)) worker.Kill(true); }
            catch (Exception error) { AppLog.Error("Gestures.Stop", error); }
            lock (sync)
            {
                if (process == worker)
                {
                    state["armed"] = false;
                    state["recording"] = false;
                    state["points"] = null;
                    state["message"] = "Câmera desligada.";
                }
            }
            OnStatusChanged?.Invoke();
        }
    }
}
