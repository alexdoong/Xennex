using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using System.Linq;
using System.Security.Cryptography;
using Xennex.Models.LocalAi;
using Xennex.Services.LocalAi;

static class AlicePanelTests
{
    public static async Task Real(string python, string checkpoint, string output, string endpoint)
    {
        var checksum = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(checkpoint)));
        var folder = Path.GetFullPath(output);
        if (Directory.Exists(folder)) throw new Exception("Real panel test requires a fresh folder.");
        Directory.CreateDirectory(folder);
        var service = new AlicePanelService(folder, Directory.GetCurrentDirectory());
        var settings = new AlicePanelSettings { Python = python, Checkpoint = checkpoint, Endpoint = endpoint, Seconds = 90, RamFraction = .9 };
        string requestId = null;
        int observations = 0, moments = 0;
        async Task<JsonElement> Ready(Func<JsonElement, bool> condition)
        {
            for (int i = 0; i < 400; i++)
            {
                using var doc = JsonDocument.Parse(await service.State());
                var value = doc.RootElement.Clone();
                if (!value.GetProperty("running").GetBoolean()) throw new Exception("Owned Alice process stopped unexpectedly; inspect stderr.log.");
                if (value.GetProperty("currentSnapshot").GetBoolean() && condition(value)) return value;
                await Task.Delay(200);
            }
            throw new Exception("Timed out waiting for Alice panel state.");
        }
        try
        {
            await service.Start(JsonSerializer.Serialize(settings, AiStore.Json));
            var state = await Ready(value => value.GetProperty("snapshot").TryGetProperty("interaction_state", out _));
            var native = state.GetProperty("snapshot").GetProperty("native_state");
            observations = native.GetProperty("observations").GetInt32(); moments = native.GetProperty("lifetime_moments").GetInt32();
            var source = state.GetProperty("snapshot").GetProperty("interaction_state").GetProperty("records").EnumerateArray()
                .First(item => item.GetProperty("status").GetString() == "completed" && item.GetProperty("request").GetProperty("action").GetString() == "relate");
            var about = source.GetProperty("request").GetProperty("id").GetString();
            var sent = await service.Send(JsonSerializer.Serialize(new { kind = "recall", payload = new { text = "E agora?", about } }));
            requestId = sent.GetProperty("id").GetString();
            JsonElement Found(JsonElement value) => value.GetProperty("snapshot").GetProperty("interaction_state").GetProperty("records").EnumerateArray()
                .FirstOrDefault(item => item.GetProperty("request").GetProperty("id").GetString() == requestId);
            var completed = await Ready(value => Found(value).ValueKind != JsonValueKind.Undefined && Found(value).GetProperty("status").GetString() is "completed" or "failed");
            var record = Found(completed);
            if (record.GetProperty("status").GetString() != "completed") throw new Exception("Real referenced query failed: " + record.GetRawText());
            var text = record.GetProperty("result").GetProperty("data").GetProperty("proposal").GetProperty("text").GetString();
            if (!text.Contains("mãe", StringComparison.OrdinalIgnoreCase)) throw new Exception("Real panel reply lost the learned correction: " + text);
            native = completed.GetProperty("snapshot").GetProperty("native_state");
            if (observations != native.GetProperty("observations").GetInt32() || moments != native.GetProperty("lifetime_moments").GetInt32()) throw new Exception("A memory query invented a perception.");
            File.WriteAllText(Path.Combine(folder, "query-state.json"), completed.GetRawText());
            await service.Stop();
            using (var stopped = JsonDocument.Parse(await service.State()))
                if (stopped.RootElement.GetProperty("running").GetBoolean()) throw new Exception("Owned process did not stop.");
            await service.Start(JsonSerializer.Serialize(settings, AiStore.Json));
            var resumed = await Ready(value => value.GetProperty("snapshot").TryGetProperty("interaction_state", out _) && Found(value).ValueKind != JsonValueKind.Undefined);
            if (Found(resumed).GetProperty("status").GetString() != "completed") throw new Exception("Panel restart lost the completed interaction.");
            File.WriteAllText(Path.Combine(folder, "resumed-state.json"), resumed.GetRawText());
            await service.Stop();
            if (Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(checkpoint))) != checksum) throw new Exception("Panel changed the selected source state.");
            File.WriteAllText(Path.Combine(folder, "audit.json"), JsonSerializer.Serialize(new { passed = true, requestId, text, observations, moments, sourceSha256 = checksum, restartVerified = true, liveSensors = false }, AiStore.Json));
            Console.WriteLine("PASS real Alice panel service: learned correction, external input, no invented perception, stop/save/restart and unchanged source.");
        }
        finally { await service.Shutdown(); }
    }

    public static async Task<int> Run()
    {
        var root = Path.Combine(Path.GetTempPath(), "alice-panel-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var service = new AlicePanelService(root, root);
        int passed = 0;
        void Check(bool value, string name) { if (!value) throw new Exception(name); passed++; Console.WriteLine("PASS " + name); }
        async Task Reject(Func<Task> action, string name)
        { try { await action(); } catch { Check(true, name); return; } throw new Exception(name); }
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "runtime"));
            File.WriteAllText(Path.Combine(root, "runtime", "status.json"), "{\"phase\":\"running\",\"ticks\":123}");
            using var doc = JsonDocument.Parse(await service.State());
            Check(!doc.RootElement.GetProperty("running").GetBoolean(), "old Alice report is not process liveness");
            Check(!doc.RootElement.GetProperty("currentSnapshot").GetBoolean(), "old report belongs to a previous execution");
            Check(doc.RootElement.GetProperty("settings").GetProperty("dialogueModel").GetString() == "", "legacy Alice settings keep the shared expression model");
            Check(doc.RootElement.GetProperty("settings").GetProperty("memoryRecall").GetString() == "preserve", "legacy Alice settings preserve the saved recall mode");
            Check(doc.RootElement.GetProperty("settings").GetProperty("mirageModels").GetString() == "", "legacy Alice settings leave automatic regions disabled");
            var validationPython = Path.Combine(root, "python.exe");
            File.WriteAllText(validationPython, "validation fixture; never executed");
            foreach (var invalid in new[] { "has space", "\n", "\0", new string('x', 129) })
            {
                try { await service.Start(JsonSerializer.Serialize(new AlicePanelSettings { Python = validationPython, DialogueModel = invalid }, AiStore.Json)); }
                catch (ArgumentException error) when (error.Message == "Nome do modelo de conversa inválido.")
                { Check(true, "Alice rejects invalid expression model before process startup"); continue; }
                throw new Exception("Invalid expression model escaped validation.");
            }
            bool invalidRecallRejected = false;
            try { await service.Start(JsonSerializer.Serialize(new AlicePanelSettings { Python = validationPython, MemoryRecall = "unknown" }, AiStore.Json)); }
            catch (ArgumentException error) when (error.Message == "Modo de evocação inválido.")
            { invalidRecallRejected = true; }
            Check(invalidRecallRejected, "Alice rejects an unknown recall mode before process startup");
            bool invalidMirageRejected = false;
            try { await service.Start(JsonSerializer.Serialize(new AlicePanelSettings { Python = validationPython, MirageModels = root }, AiStore.Json)); }
            catch (ArgumentException error) when (error.Message.StartsWith("Selecione a pasta local do Mirage", StringComparison.Ordinal))
            { invalidMirageRejected = true; }
            Check(invalidMirageRejected, "Alice requires configured perception and local assets to enable Mirage");
            await Reject(() => service.Send("{\"kind\":\"ask\",\"payload\":{\"text\":\"Oi?\"}}"), "Alice rejects input before start");
            await Reject(() => service.Perceive("image", "missing.png"), "Alice rejects perception before start");
            await Reject(() => service.PerceivePair("missing.png", "missing.wav"), "Alice rejects paired perception before start");
            await Reject(() => service.PerceiveWordAudio("missing.wav", "água"), "Alice rejects word practice before start");
            await Reject(() => service.Start("{\"python\":\"cmd.exe\"}"), "Alice never executes a selected command shell");
            await Reject(() => service.Start("{\"unexpected\":true}"), "Alice rejects unknown configuration fields");
            await service.Stop(); await service.Shutdown();
            await Reject(() => service.Start("{}"), "Alice cannot restart during application shutdown");
        }
        finally { Directory.Delete(root, true); }
        return passed;
    }
}
