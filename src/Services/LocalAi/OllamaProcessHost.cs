using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;

namespace Xennex.Services.LocalAi;

/// <summary>Owns only the server it starts. Never stops a pre-existing Ollama.</summary>
public sealed class OllamaProcessHost
{
    public const string Endpoint = "http://127.0.0.1:11436/v1";
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly object sync = new();
    private Process owned;
    private bool stopped;
    private readonly string modelsDirectory;
    public OllamaProcessHost(string modelsDirectory = null) { this.modelsDirectory = modelsDirectory; }
    public string ModelsDirectory => modelsDirectory != null && Directory.Exists(Path.Combine(modelsDirectory, "manifests")) ? modelsDirectory : "";
    public string InstalledPath()
    {
        try
        {
            var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Ollama", "ollama.exe");
            return File.Exists(path) ? path : "";
        }
        catch (Exception error) { AppLog.Error("LocalAi.Ollama.Detect", error); return ""; }
    }
    public bool Owns(string endpoint)
    {
        lock (sync)
        {
            try { return LocalModelClient.Endpoint(endpoint) == LocalModelClient.Endpoint(Endpoint) && owned != null && !owned.HasExited; }
            catch (Exception error) { AppLog.Error("LocalAi.Ollama.Status", error); return false; }
        }
    }
    public async Task Start(IOllamaRuntimeClient runtime, CancellationToken token)
    {
        await gate.WaitAsync(token);
        try
        {
            lock (sync)
            {
                if (stopped) throw new InvalidOperationException("O aplicativo está encerrando.");
                if (Owns(Endpoint)) return;
                var path = InstalledPath();
                if (path == "") throw new FileNotFoundException("Ollama não encontrado na instalação padrão. Instale o motor ou configure um servidor já iniciado.");
                // Fail if another server uses the private port; never adopt it as an owned process.
                var listener = new TcpListener(IPAddress.Loopback, 11436);
                try { listener.Start(); } finally { listener.Stop(); }
                var start = new ProcessStartInfo(path, "serve") { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
                start.Environment["OLLAMA_HOST"] = "127.0.0.1:11436";
                if (ModelsDirectory != "") start.Environment["OLLAMA_MODELS"] = ModelsDirectory;
                start.Environment["OLLAMA_NO_CLOUD"] = "1";
                start.Environment["OLLAMA_NUM_PARALLEL"] = "1";
                start.Environment["OLLAMA_MAX_LOADED_MODELS"] = "1";
                start.Environment["OLLAMA_CONTEXT_LENGTH"] = "4096";
                start.Environment["OLLAMA_KEEP_ALIVE"] = "60s";
                start.Environment["OLLAMA_MAX_QUEUE"] = "1";
                owned?.Dispose(); owned = Process.Start(start) ?? throw new IOException("O motor não iniciou.");
            }
            while (true)
            {
                token.ThrowIfCancellationRequested();
                if (!Owns(Endpoint)) throw new IOException("O processo do Ollama encerrou durante a inicialização.");
                try { await runtime.Inspect(Endpoint, token); return; }
                catch (System.Net.Http.HttpRequestException) { await Task.Delay(400, token); }
            }
        }
        catch (Exception error) { AppLog.Error("LocalAi.Ollama.Start", error); StopOwned(); throw; }
        finally { gate.Release(); }
    }
    private void StopOwned()
    {
        lock (sync)
        {
            try { if (owned != null && !owned.HasExited) owned.Kill(entireProcessTree: true); }
            catch (Exception error) { AppLog.Error("LocalAi.Ollama.Stop", error); }
            finally { owned?.Dispose(); owned = null; }
        }
    }
    public void Stop() { lock (sync) { stopped = true; StopOwned(); } }
}
