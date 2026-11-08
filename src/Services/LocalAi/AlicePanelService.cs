using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

/// <summary>Owns one explicit experimental session, not the local AI chat engine.</summary>
public sealed class AlicePanelService
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow
    };
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly string root, scripts;
    private Process owner;
    private AlicePanelSettings settings = new();
    private bool loaded;
    private string lastError = "";
    private Task outputDrain = Task.CompletedTask, errorDrain = Task.CompletedTask;
    private DateTime startedUtc = DateTime.MaxValue;
    private volatile bool closing;

    public AlicePanelService(string directory = null, string scriptDirectory = null)
    {
        root = Path.GetFullPath(directory ?? Path.Combine(AppContext.BaseDirectory, "Data", "ai", "alice"));
        scripts = Path.GetFullPath(scriptDirectory ?? AppContext.BaseDirectory);
    }

    private bool Running => owner is not null && !owner.HasExited;
    private string Owned(string name)
    {
        var path = Path.GetFullPath(Path.Combine(root, name));
        if (!path.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Caminho fora da sessão da Alice.");
        for (var current = path; current is not null && current.StartsWith(root, StringComparison.OrdinalIgnoreCase); current = Path.GetDirectoryName(current))
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("A sessão da Alice não aceita redirecionamentos de pasta.");
        return path;
    }

    private void Load()
    {
        if (loaded) return;
        var file = Owned("settings.json");
        if (File.Exists(file)) settings = JsonSerializer.Deserialize<AlicePanelSettings>(Read(file, 16384), Json)
            ?? throw new InvalidDataException("Configuração da Alice inválida.");
        if (string.IsNullOrEmpty(settings.Python))
        {
            var candidate = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python311", "python.exe");
            if (File.Exists(candidate)) settings.Python = candidate;
        }
        loaded = true;
    }

    private static string Read(string path, long limit)
    {
        var file = new FileInfo(path);
        if (file.Length > limit || (file.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Arquivo da sessão inválido ou grande demais.");
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        using var reader = new StreamReader(stream, Encoding.UTF8);
        return reader.ReadToEnd();
    }

    private static void Validate(AlicePanelSettings value)
    {
        if (value is null || !File.Exists(value.Python) || Path.GetFileName(value.Python).ToLowerInvariant() != "python.exe")
            throw new ArgumentException("Selecione o python.exe instalado com as dependências da Alice.");
        if (value.Model is null || value.Model.Length is < 1 or > 128 || value.Model.IndexOfAny(new[] {'\r','\n','\0'}) >= 0)
            throw new ArgumentException("Nome de modelo inválido.");
        if (value.DialogueModel is null || value.DialogueModel.Length > 128 || value.DialogueModel.Any(char.IsWhiteSpace) || value.DialogueModel.Contains('\0'))
            throw new ArgumentException("Nome do modelo de conversa inválido.");
        if (!Uri.TryCreate(value.Endpoint, UriKind.Absolute, out var uri) || uri.Scheme != "http" || uri.UserInfo != "" || uri.Query != "" || uri.Fragment != "" ||
            !(uri.Host == "localhost" || IPAddress.TryParse(uri.Host, out var address) && IPAddress.IsLoopback(address)) ||
            uri.AbsolutePath is not ("/" or "/v1" or "/v1/"))
            throw new ArgumentException("Use o endereço HTTP local do Ollama.");
        value.Endpoint = uri.GetLeftPart(UriPartial.Authority);
        if (value.Attention is not ("full" or "learned" or "quiet"))
            throw new ArgumentException("Modo de atenção inválido.");
        if (value.MemoryRecall is not ("preserve" or "enabled" or "disabled"))
            throw new ArgumentException("Modo de evocação inválido.");
        if (value.Seconds is < 0 or > 3600 || !double.IsFinite(value.RamFraction) || value.RamFraction is < .5 or > .9 || value.RamFraction > .75 && value.Seconds == 0)
            throw new ArgumentException("Acima de 75% de RAM, configure um teste com duração limitada.");
        if (value.PerceptionPython is null || value.PerceptionModels is null || (value.PerceptionPython == "") != (value.PerceptionModels == ""))
            throw new ArgumentException("Selecione juntos o interpretador e a pasta do encoder perceptivo.");
        if (value.PerceptionPython != "" && (!File.Exists(value.PerceptionPython) || Path.GetFileName(value.PerceptionPython).ToLowerInvariant() != "python.exe" || !Directory.Exists(value.PerceptionModels)))
            throw new ArgumentException("Dependências da percepção não encontradas.");
        if (value.MirageModels is null || (value.MirageModels != "" &&
            (value.PerceptionPython == "" || !Directory.Exists(value.MirageModels) ||
             !File.Exists(Path.Combine(value.MirageModels, "libcactus.dll")) || !File.Exists(Path.Combine(value.MirageModels, "mirage.cact")))))
            throw new ArgumentException("Selecione a pasta local do Mirage com a percepção configurada.");
    }

    private ProcessStartInfo Command(string module)
    {
        var start = new ProcessStartInfo(settings.Python) { WorkingDirectory = scripts, UseShellExecute = false,
            CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
        start.ArgumentList.Add("-m"); start.ArgumentList.Add(module);
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        start.Environment["ALICE_EXPERIMENT_RAM_FRACTION"] = settings.RamFraction.ToString(System.Globalization.CultureInfo.InvariantCulture);
        return start;
    }

    private async Task<JsonElement> Request(object request)
    {
        var start = Command("scripts.alice_memory.ui_gateway");
        start.ArgumentList.Add("--root"); start.ArgumentList.Add(root);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Não foi possível iniciar a ponte da Alice.");
        try
        {
            var output = process.StandardOutput.ReadToEndAsync(); var error = process.StandardError.ReadToEndAsync();
            await process.StandardInput.WriteAsync(JsonSerializer.Serialize(request, Json)); process.StandardInput.Close();
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
            await process.WaitForExitAsync(timeout.Token);
            var text = await output; var diagnostic = await error;
            if (process.ExitCode != 0 || text.Length > 65536)
                throw new InvalidOperationException("A ponte da Alice não concluiu: " + diagnostic[..Math.Min(diagnostic.Length, 2048)]);
            using var document = JsonDocument.Parse(text);
            if (!document.RootElement.GetProperty("ok").GetBoolean())
                throw new InvalidOperationException(document.RootElement.GetProperty("error").GetString());
            return document.RootElement.GetProperty("value").Clone();
        }
        finally
        {
            if (!process.HasExited) process.Kill(true);
            await process.WaitForExitAsync();
        }
    }

    public async Task<string> State()
    {
        await gate.WaitAsync();
        try
        {
            Load(); JsonElement? snapshot = null;
            var path = Owned(Path.Combine("runtime", "status.json"));
            var currentSnapshot = File.Exists(path) && File.GetLastWriteTimeUtc(path) >= startedUtc;
            if (File.Exists(path)) { using var doc = JsonDocument.Parse(Read(path, 2 * 1024 * 1024)); snapshot = doc.RootElement.Clone(); }
            return JsonSerializer.Serialize(new { settings, running = Running, lastError, directory = root,
                scriptsAvailable = File.Exists(Path.Combine(scripts, "scripts", "alice_memory", "persistent_runtime.py")), currentSnapshot, snapshot,
                exitCode = owner is not null && owner.HasExited ? (int?)owner.ExitCode : null }, Json);
        }
        catch (Exception error) { AppLog.Error("Alice.State", error); throw; }
        finally { gate.Release(); }
    }

    public async Task Start(string json)
    {
        await gate.WaitAsync();
        try
        {
            Load(); if (closing) throw new InvalidOperationException("O aplicativo está encerrando a Alice.");
            if (Running) throw new InvalidOperationException("A sessão já está em execução.");
            if (json is null || json.Length > 16384) throw new ArgumentException("Configuração inválida.");
            var next = JsonSerializer.Deserialize<AlicePanelSettings>(json, Json); Validate(next);
            if (!File.Exists(Path.Combine(scripts, "scripts", "alice_memory", "persistent_runtime.py")))
                throw new InvalidOperationException("Scripts experimentais da Alice não estão neste build.");
            Directory.CreateDirectory(root); settings = next;
            if (!File.Exists(Owned(Path.Combine("runtime", "current.json"))) && !File.Exists(Owned("seed.pt")) && !File.Exists(settings.Checkpoint))
                throw new ArgumentException("Selecione um arquivo de estado compatível para iniciar a primeira sessão.");
            await Request(new { action = "prepare", checkpoint = settings.Checkpoint });
            var settingsTemp = Owned("settings.tmp");
            File.WriteAllText(settingsTemp, JsonSerializer.Serialize(settings, Json), new UTF8Encoding(false));
            File.Move(settingsTemp, Owned("settings.json"), true);
            var stopRequest = Owned(Path.Combine("runtime", "stop.request"));
            if (File.Exists(stopRequest)) File.Delete(stopRequest);
            await Task.WhenAll(outputDrain, errorDrain);
            var start = Command("scripts.alice_memory.persistent_runtime");
            void Option(string key, string value) { start.ArgumentList.Add(key); start.ArgumentList.Add(value); }
            Option("--store", Owned("runtime")); Option("--checkpoint", Owned("seed.pt"));
            Option("--interaction-inbox", Owned("human")); Option("--endpoint", settings.Endpoint); Option("--model", settings.Model);
            Option("--dialogue-model", settings.DialogueModel);
            Option("--native-attention", settings.Attention);
            if (settings.MemoryRecall == "enabled") start.ArgumentList.Add("--native-implicit-recall");
            if (settings.MemoryRecall == "disabled") start.ArgumentList.Add("--no-native-implicit-recall");
            if (settings.Seconds > 0) Option("--seconds", settings.Seconds.ToString());
            if (settings.PerceptionPython != "")
            {
                Option("--native-inbox", Owned("sensory")); Option("--native-models", settings.PerceptionModels);
                Option("--native-interpreter", settings.PerceptionPython); Option("--native-ram-fraction", settings.RamFraction.ToString(System.Globalization.CultureInfo.InvariantCulture));
            }
            if (settings.MirageModels != "") Option("--native-mirage", settings.MirageModels);
            if (closing) throw new InvalidOperationException("O aplicativo está encerrando a Alice.");
            owner?.Dispose(); startedUtc = DateTime.UtcNow;
            owner = Process.Start(start) ?? throw new InvalidOperationException("Não foi possível iniciar a Alice.");
            owner.StandardInput.Close(); lastError = "";
            outputDrain = Drain(owner.StandardOutput, "stdout.log"); errorDrain = Drain(owner.StandardError, "stderr.log");
        }
        catch (Exception error) { lastError = error.Message; AppLog.Error("Alice.Start", error); throw; }
        finally { gate.Release(); }
    }

    private async Task Drain(StreamReader reader, string name)
    {
        try
        {
            using var file = new StreamWriter(Owned(name), false, new UTF8Encoding(false));
            char[] buffer = new char[2048]; int count, total = 0;
            while ((count = await reader.ReadAsync(buffer)) > 0)
            { if (total < 200000) { await file.WriteAsync(buffer.AsMemory(0, Math.Min(count, 200000 - total))); total += count; } }
        }
        catch (Exception error) { AppLog.Error("Alice.Log", error); }
    }

    public async Task<JsonElement> Send(string json)
    {
        await gate.WaitAsync();
        try
        {
            Load(); if (!Running) throw new InvalidOperationException("Inicie a sessão da Alice antes de enviar.");
            if (json is null || json.Length > 16384) throw new ArgumentException("Mensagem inválida.");
            using var doc = JsonDocument.Parse(json);
            var value = doc.RootElement;
            if (value.ValueKind != JsonValueKind.Object || value.EnumerateObject().Count() != 2)
                throw new ArgumentException("Mensagem deve conter somente kind e payload.");
            return await Request(new { action = "send", kind = value.GetProperty("kind").GetString(), payload = value.GetProperty("payload").Clone() });
        }
        catch (Exception error) { AppLog.Error("Alice.Send", error); throw; }
        finally { gate.Release(); }
    }

    public Task<JsonElement> Perceive(string modality, string path) =>
        PerceiveFiles(new { action = "perceive", modality, path });

    public Task<JsonElement> PerceivePair(string image, string audio) =>
        PerceiveFiles(new { action = "perceive_pair", image, audio });

    public Task<JsonElement> PerceiveWordAudio(string path, string word) =>
        PerceiveFiles(new { action = "word_audio", path, word = string.IsNullOrWhiteSpace(word) ? null : word });

    private async Task<JsonElement> PerceiveFiles(object request)
    {
        await gate.WaitAsync();
        try
        {
            Load(); if (!Running || settings.PerceptionPython == "") throw new InvalidOperationException("Inicie a sessão com percepção de arquivos configurada.");
            return await Request(request);
        }
        catch (Exception error) { AppLog.Error("Alice.Perceive", error); throw; }
        finally { gate.Release(); }
    }

    public async Task<JsonElement> PerceiveText(string text)
    {
        await gate.WaitAsync();
        try
        {
            Load(); if (!Running || settings.PerceptionPython == "") throw new InvalidOperationException("Configure a percepção de texto e inicie a Alice antes de conversar.");
            if (text is null || text.Length > 4096) throw new ArgumentException("Mensagem de texto inválida.");
            return await Request(new { action = "text", text });
        }
        catch (Exception error) { AppLog.Error("Alice.Text", error); throw; }
        finally { gate.Release(); }
    }

    public async Task Stop()
    {
        await gate.WaitAsync();
        try
        {
            if (!Running) { await Task.WhenAll(outputDrain, errorDrain); return; }
            File.WriteAllText(Owned(Path.Combine("runtime", "stop.request")), "stop", new UTF8Encoding(false));
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            try { await owner.WaitForExitAsync(timeout.Token); }
            catch (OperationCanceledException) { if (!owner.HasExited) owner.Kill(true); await owner.WaitForExitAsync(); }
            await Task.WhenAll(outputDrain, errorDrain);
        }
        catch (Exception error) { AppLog.Error("Alice.Stop", error); throw; }
        finally { gate.Release(); }
    }

    public async Task Shutdown()
    {
        closing = true;
        await Stop();
        await gate.WaitAsync();
        try { owner?.Dispose(); owner = null; }
        finally { gate.Release(); }
    }
}
