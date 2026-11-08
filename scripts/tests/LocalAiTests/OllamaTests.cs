using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;
using Xennex.Services.LocalAi;

internal static class OllamaTests
{
    private static JsonElement State(LocalAiService service) => JsonDocument.Parse(service.GetState()).RootElement.Clone();
    private static JsonElement Job(LocalAiService service, string id) => State(service).GetProperty("jobs").EnumerateArray().Single(j => j.GetProperty("id").GetString() == id);
    private static async Task Wait(Func<bool> done, int seconds = 10)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
        while (!done()) await Task.Delay(50, timeout.Token);
    }
    public static async Task<int> Run()
    {
        int passed = 0;
        void Check(bool condition, string name) { if (!condition) throw new Exception(name); Console.WriteLine("PASS " + name); passed++; }
        var settings = new AiSettings { Provider = "ollama", AutoBudget = true, Model = "local-test", ContextTokens = 2048, MaxOutputTokens = 128 };
        var model = new OllamaModel { Name = "local-test", Digest = "digest-a", DiskGb = 4 };
        var info = new OllamaModelInfo { LocalCompletion = true, CacheBytesPerToken = 131072 };
        var measurements = new List<ResourceMeasurement>();
        var cold = ModelMemoryEstimator.Estimate(settings, model, info, measurements);
        model.Loaded = true; model.PlacementKnown = true; model.LoadedContext = 2048; model.LoadedVramGb = 4.5;
        var warm = ModelMemoryEstimator.Estimate(settings, model, info, measurements);
        var resources = new ResourceSnapshot { RamTotalGb = 32, RamUsedGb = 20, VramTotalGb = 16, VramUsedGb = 8 };
        var admission = new AiSettings { AdditionalRamGb = warm.RamGb, AdditionalVramGb = warm.VramGb };
        Check(warm.AlreadyLoaded && warm.RamGb < cold.RamGb && ResourcePolicy.Check(resources, admission, true) == "", "resident weights do not block the next request by double reservation");
        settings.ContextTokens = 4096;
        Check(!ModelMemoryEstimator.Estimate(settings, model, info, measurements).AlreadyLoaded, "larger context requires a new loading reservation");
        settings.ContextTokens = 2048; settings.UseGpu = false;
        Check(!ModelMemoryEstimator.Estimate(settings, model, info, measurements).AlreadyLoaded, "switching GPU to CPU cannot reuse GPU residency");
        model.PlacementKnown = false;
        Check(!ModelMemoryEstimator.Estimate(settings, model, info, measurements).AlreadyLoaded, "missing model placement is not assumed to be CPU residency");
        model.PlacementKnown = true;
        settings.UseGpu = true;
        ModelMemoryEstimator.Observe(measurements, warm, 3, 2);
        ModelMemoryEstimator.Observe(measurements, warm, .5, .5);
        var observed = ModelMemoryEstimator.Estimate(settings, model, info, measurements);
        Check(observed.RamGb > 3 && observed.Source == "observed", "observed deltas raise future reservations and never lower them");
        model.Digest = "digest-b";
        Check(ModelMemoryEstimator.Estimate(settings, model, info, measurements).Source == "estimate", "replaced model does not reuse stale observations");
        try { OllamaChatClient.CheckContext(settings, new[] { new AiMessage { Content = new string('x', 4000) } }); throw new Exception("Expected context guard"); }
        catch (InvalidOperationException) { Check(true, "oversized context rejected without silently dropping history"); }
        var handler = new OllamaHandler();
        var runtime = new OllamaRuntimeClient(handler);
        var snapshot = await runtime.Inspect(settings.Endpoint, CancellationToken.None);
        Check(snapshot.Models.Single().LoadedContext == 2048 && snapshot.Models[0].DiskGb == 4, "native metadata separates disk weights and loaded context");
        var described = await runtime.Describe(settings.Endpoint, settings.Model, CancellationToken.None);
        Check(described.LocalCompletion && described.CacheBytesPerToken == 131072, "architecture metadata yields KV cache estimate");
        var client = new LocalModelClient(handler); var output = new StringBuilder(); settings.UseGpu = false; settings.KeepAliveSeconds = 0;
        await client.Stream(settings, new[] { new AiMessage { Content = "oi" } }, s => output.Append(s), CancellationToken.None);
        var body = JsonDocument.Parse(handler.ChatBody).RootElement;
        Check(output.ToString() == "Olá!" && body.GetProperty("options").GetProperty("num_gpu").GetInt32() == 0 && body.GetProperty("options").GetProperty("num_ctx").GetInt32() == 2048 && body.GetProperty("keep_alive").GetInt32() == 0, "native stream enforces CPU, context, residency and completion");
        handler.Truncated = true;
        try { await client.Stream(settings, Array.Empty<AiMessage>(), _ => { }, CancellationToken.None); throw new Exception("Expected EOF rejection"); }
        catch (IOException) { Check(true, "truncated native stream is not a successful response"); }
        handler.Remote = true; handler.ChatBody = "";
        try { await client.Stream(settings, Array.Empty<AiMessage>(), _ => { }, CancellationToken.None); throw new Exception("Expected cloud rejection"); }
        catch (InvalidOperationException) { Check(handler.ChatBody == "", "remote model rejected before prompts reach chat endpoint"); }
        var root = Path.Combine(Path.GetTempPath(), "Xennex-OllamaTests-" + Guid.NewGuid().ToString("N"));
        var fakeRuntime = new FakeRuntime(); var fakeModel = new CompletingModel(fakeRuntime); var probe = new MutableProbe();
        var service = new LocalAiService(root, fakeModel, probe, fakeRuntime);
        try
        {
            settings.UseGpu = true; settings.KeepAliveSeconds = 60;
            service.SaveSettings(JsonSerializer.Serialize(settings, AiStore.Json));
            string chat = service.NewChat(); string first = service.Send(chat, "primeiro");
            await Wait(() => Job(service, first).GetProperty("status").GetString() == "complete");
            probe.Ram = 20;
            string second = service.Send(chat, "segundo");
            await Wait(() => Job(service, second).GetProperty("status").GetString() == "complete");
            Check(fakeModel.Calls == 2 && Job(service, second).GetProperty("demand").GetProperty("alreadyLoaded").GetBoolean(), "queue refreshes residency between consecutive turns");
            Check(new AiStore(root).Load().Measurements.Count == 2, "cold and warm observations persist separately");
            fakeRuntime.Delay = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            string cancelled = service.Send(service.NewChat(), "cancelar na inspeção");
            await Wait(() => fakeRuntime.Inspecting);
            service.Cancel(cancelled); fakeRuntime.Delay.SetResult();
            await Task.Delay(200);
            Check(fakeModel.Calls == 2 && Job(service, cancelled).GetProperty("status").GetString() == "cancelled", "cancellation during metadata query cannot dispatch inference");
            try { await service.ReleaseModel(); throw new Exception("Expected external ownership rejection"); }
            catch (InvalidOperationException) { Check(fakeRuntime.Unloads == 0, "release never unloads an external server model"); }
            var restored = new AiStore(root).Load();
            restored.Settings = JsonSerializer.Deserialize<AiSettings>("{\"model\":\"legacy\"}", AiStore.Json);
            new AiStore(root).Save(restored);
            Check(new AiStore(root).Load().Settings.Provider == "compatible", "legacy configuration retains compatible manual mode");
        }
        finally { service.Stop(); if (Directory.Exists(root)) Directory.Delete(root, true); }
        return passed;
    }
    public static async Task Real(string model)
    {
        var directory = Path.Combine(Path.GetTempPath(), "Xennex-OllamaReal-" + Guid.NewGuid().ToString("N"));
        var service = new LocalAiService(directory);
        var runtime = new OllamaRuntimeClient();
        try
        {
            Console.WriteLine("Starting owned Ollama (existing weights only)");
            Console.WriteLine(await service.StartRuntime());
            var settings = new AiSettings { Provider = "ollama", Endpoint = OllamaProcessHost.Endpoint, Model = model, AutoBudget = true, ContextTokens = 2048, MaxOutputTokens = 128, KeepAliveSeconds = 60, MemoryLimitPercent = 85 };
            service.SaveSettings(JsonSerializer.Serialize(settings, AiStore.Json));
            string chat = service.NewChat();
            foreach (var prompt in new[] { "Quanto é 2 + 2? Responda com uma frase curta.", "E quanto é 3 + 3? Responda com uma frase curta." })
            {
                string id = service.Send(chat, prompt);
                await Wait(() => Job(service, id).GetProperty("status").GetString() is not ("running" or "queued"), 100);
                var job = Job(service, id); Console.WriteLine(job.ToString());
                if (job.GetProperty("status").GetString() != "complete") throw new Exception("Real inference failed: " + job);
                var answer = State(service).GetProperty("chats")[0].GetProperty("messages").EnumerateArray().Last().GetProperty("content").GetString();
                Console.WriteLine(answer);
                if (string.IsNullOrWhiteSpace(answer)) throw new Exception("Empty real response");
            }
            var last = State(service).GetProperty("jobs").EnumerateArray().Last();
            if (!last.GetProperty("demand").GetProperty("alreadyLoaded").GetBoolean()) throw new Exception("Second turn did not reuse resident model");
            await service.ReleaseModel();
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            if ((await runtime.Inspect(settings.Endpoint, timeout.Token)).Models.Any(m => m.Loaded)) throw new Exception("Unload not confirmed");
            Console.WriteLine("Real Ollama: two sequential answers, automatic admission, resident reuse and explicit unload PASS");
        }
        finally { service.Stop(); if (Directory.Exists(directory)) Directory.Delete(directory, true); }
    }
    private sealed class OllamaHandler : HttpMessageHandler
    {
        public bool Remote, Truncated;
        public string ChatBody = "";
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string path = request.RequestUri.AbsolutePath;
            string json = path switch
            {
                "/api/tags" => "{\"models\":[{\"name\":\"local-test\",\"digest\":\"a\",\"size\":4294967296}]}",
                "/api/ps" => "{\"models\":[{\"name\":\"local-test\",\"digest\":\"a\",\"size\":4831838208,\"size_vram\":4294967296,\"context_length\":2048}]}",
                "/api/show" => JsonSerializer.Serialize(new { remote_host = Remote ? "https://remote.test" : "", capabilities = new[] { "completion" }, model_info = new Dictionary<string, object> { ["general.architecture"] = "llama", ["llama.block_count"] = 32, ["llama.attention.head_count"] = 32, ["llama.attention.head_count_kv"] = 8, ["llama.embedding_length"] = 4096 } }),
                "/api/chat" => "{\"message\":{\"content\":\"Olá!\"},\"done\":false}\n" + (Truncated ? "" : "{\"done\":true}\n"),
                _ => throw new Exception("Unexpected native route: " + path)
            };
            if (path == "/api/chat") ChatBody = await request.Content.ReadAsStringAsync(token);
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(json) };
        }
    }
    private sealed class FakeRuntime : IOllamaRuntimeClient
    {
        public bool Loaded, Inspecting; public int Unloads; public TaskCompletionSource Delay;
        public async Task<OllamaSnapshot> Inspect(string endpoint, CancellationToken token)
        {
            if (Delay != null) { Inspecting = true; await Delay.Task.WaitAsync(token); }
            return new() { Endpoint = endpoint, Models = new() { new() { Name = "local-test", Digest = "a", DiskGb = 4, Loaded = Loaded, PlacementKnown = true, LoadedVramGb = Loaded ? 4.5 : 0, LoadedContext = Loaded ? 2048 : 0 } } };
        }
        public Task<OllamaModelInfo> Describe(string endpoint, string model, CancellationToken token) => Task.FromResult(new OllamaModelInfo { LocalCompletion = true, CacheBytesPerToken = 131072 });
        public Task Unload(string endpoint, string model, CancellationToken token) { Unloads++; return Task.CompletedTask; }
    }
    private sealed class CompletingModel : ILocalModelClient
    {
        private readonly FakeRuntime runtime; public int Calls;
        public CompletingModel(FakeRuntime runtime) { this.runtime = runtime; }
        public Task<string[]> Models(AiSettings settings, CancellationToken token) => Task.FromResult(new[] { "local-test" });
        public async Task Stream(AiSettings settings, AiMessage[] history, Action<string> append, CancellationToken token)
        { Calls++; await Task.Delay(50, token); runtime.Loaded = true; append("resposta curta"); }
    }
}
