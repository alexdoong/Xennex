using System;
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

if (args.Length == 1 && args[0] == "--resources")
{
    if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("Windows resource telemetry required.");
    Console.WriteLine(JsonSerializer.Serialize(new WindowsResourceProbe().Read(), AiStore.Json));
    return;
}
if (args.Length == 5 && args[0] == "--alice-panel-real") { await AlicePanelTests.Real(args[1], args[2], args[3], args[4]); return; }
if (args.Length == 2 && args[0] == "--conversation-real") { await ConversationRealTest.Run(args[1]); return; }
if (args.Length == 2 && args[0] == "--rooms-real") { await RoomRealTest.Run(args[1]); return; }
if (args.Length == 2 && args[0] == "--owned-real") { await OllamaTests.Real(args[1]); return; }
if (args.Length == 3 && args[0] == "--real")
{
    var realSettings = new AiSettings { Endpoint = args[1], Model = args[2], AdditionalRamGb = 6, AdditionalVramGb = 6, MaxOutputTokens = 128 };
    LocalModelClient.ValidateSettings(realSettings);
    var before = new WindowsResourceProbe().Read();
    Console.WriteLine("Before: " + JsonSerializer.Serialize(before, AiStore.Json));
    var reason = ResourcePolicy.Check(before, realSettings, true);
    if (reason != "") throw new Exception("Real model test not admitted: " + reason);
    using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
    var timer = System.Diagnostics.Stopwatch.StartNew();
    var answer = new StringBuilder();
    await new LocalModelClient().Stream(realSettings,
        new[] { new AiMessage { Content = "Responda em português em uma frase curta: quanto é 2 + 2?" } },
        text => { answer.Append(text); Console.Write(text); }, timeout.Token);
    Console.WriteLine("\nActual model elapsed seconds: " + timer.Elapsed.TotalSeconds.ToString("0.0"));
    Console.WriteLine("After: " + JsonSerializer.Serialize(new WindowsResourceProbe().Read(), AiStore.Json));
    if (answer.Length == 0 || !answer.ToString().Contains("4")) throw new Exception("Unexpected arithmetic response");
    Console.WriteLine("Real local model: PASS");
    return;
}
int passed = 0;
void Check(bool condition, string name) { if (!condition) throw new Exception(name); Console.WriteLine("PASS " + name); passed++; }
void Reject(Action action, string name) { try { action(); } catch { Check(true, name); return; } throw new Exception(name); }
JsonElement State(LocalAiService service) => JsonDocument.Parse(service.GetState()).RootElement.Clone();
async Task Wait(Func<bool> condition, string name)
{
    for (int i = 0; i < 160; i++) { if (condition()) { Check(true, name); return; } await Task.Delay(50); }
    throw new Exception("Timeout: " + name);
}
string JobStatus(LocalAiService service, string id) => State(service).GetProperty("jobs").EnumerateArray().Single(j => j.GetProperty("id").GetString() == id).GetProperty("status").GetString();
var settings = new AiSettings { Model = "local-test", AdditionalRamGb = 2, AdditionalVramGb = 2 };
ResourceSnapshot Snapshot(double ram = 8, double vram = 2) => new() { RamTotalGb = 32, RamUsedGb = ram, VramTotalGb = 16, VramUsedGb = vram };
Check(ResourcePolicy.Check(Snapshot(), settings, true) == "", "admits within RAM and VRAM budgets");
Check(ResourcePolicy.Check(Snapshot(23), settings, true).Contains("RAM"), "reserves additional RAM before admission");
Check(ResourcePolicy.Check(Snapshot(8, 11), settings, true).Contains("VRAM"), "VRAM is an independent budget");
Check(ResourcePolicy.Check(Snapshot(8, 11), settings, false) == "", "running job does not double count its reserve");
Check(ResourcePolicy.Check(Snapshot(25), settings, false) != "", "external memory pressure blocks running job");
Check(ResourcePolicy.Check(new ResourceSnapshot(), settings, true) != "", "missing telemetry fails closed");
var missingGpu = Snapshot(); missingGpu.VramUsedGb = null;
Check(ResourcePolicy.Check(missingGpu, settings, true).Contains("VRAM"), "unknown VRAM is not zero");
var stale = Snapshot(); stale.CapturedAt = DateTimeOffset.UtcNow.AddSeconds(-20);
Check(ResourcePolicy.Check(stale, settings, true) != "", "stale samples cannot admit work");
var impossible = new AiSettings { AdditionalRamGb = 64 };
Check(ResourcePolicy.Check(Snapshot(), impossible, true).Contains("não cabe"), "oversized indivisible demand is not admitted");
foreach (var address in new[] { "https://example.com/v1", "http://127.0.0.1.evil.test/v1", "http://user:password@127.0.0.1/v1", "http://localhost/v1", "file:///v1", "http://127.0.0.1/v1?redirect=1" })
    Reject(() => LocalModelClient.Endpoint(address), "reject endpoint " + address);
Check(LocalModelClient.Endpoint("http://127.0.0.1:1234/v1").IsLoopback, "literal loopback accepted");
Reject(() => LocalModelClient.ValidateSettings(new AiSettings { AdditionalRamGb = double.NaN }), "reject nonfinite memory estimates");
var http = new ScriptedHandler(); var client = new LocalModelClient(http);
http.Response = "{\"data\":[{\"id\":\"test\"}]}";
Check((await client.Models(settings, CancellationToken.None)).Single() == "test", "local model catalog parsed");
http.Response = "data: {\"choices\":[{\"delta\":{\"content\":\"Olá \"}}]}\n\ndata: {\"choices\":[{\"delta\":{\"content\":\"mundo\"}}]}\n\ndata: [DONE]\n";
var output = new StringBuilder();
await client.Stream(settings, new[] { new AiMessage { Content = "oi" } }, text => output.Append(text), CancellationToken.None);
Check(output.ToString() == "Olá mundo", "streaming SSE assembles UTF-8 text");
Check(http.LastBody.Contains("\"stream\":true") && http.LastBody.Contains("\"max_tokens\":1024"), "request bounds output and streams");
http.Response = "data: {\"choices\":[{\"delta\":{\"content\":\"parcial\"}}]}\n";
try { await client.Stream(settings, Array.Empty<AiMessage>(), _ => { }, CancellationToken.None); throw new Exception("Expected premature EOF"); }
catch (IOException) { Check(true, "premature stream EOF is failure, not success"); }
http.Status = HttpStatusCode.TemporaryRedirect;
try { await client.Models(settings, CancellationToken.None); throw new Exception("Expected redirect rejection"); }
catch (HttpRequestException) { Check(true, "redirect responses are rejected"); }

var root = Path.Combine(Path.GetTempPath(), "Xennex-LocalAiTests-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    var probe = new MutableProbe(); var model = new FakeModel();
    var service = new LocalAiService(root, model, probe);
    service.SaveSettings(JsonSerializer.Serialize(settings, AiStore.Json));
    var chat1 = service.NewChat(); var chat2 = service.NewChat();
    service.Pause(true);
    var first = service.Send(chat1, "Primeiro"); var second = service.Send(chat2, "Segundo");
    Check(model.Calls == 0, "paused queue does not invoke model");
    Reject(() => service.Send(chat1, "duplicado"), "same chat cannot execute concurrent turns");
    Reject(() => service.SaveSettings(JsonSerializer.Serialize(settings, AiStore.Json)), "configuration is stable while jobs wait");
    Reject(() => service.DeleteChat(chat1), "cannot delete queued conversation");
    service.Pause(false);
    await Wait(() => JobStatus(service, first) == "running", "FIFO first request starts");
    Check(JobStatus(service, second) == "queued" && model.MaxConcurrent == 1, "second request cannot overbook resources");
    await Wait(() => State(service).GetProperty("chats").EnumerateArray().Single(c => c.GetProperty("id").GetString() == chat1).GetProperty("messages")[1].GetProperty("content").GetString() == "parcial", "partial response visible while running");
    service.Cancel(first);
    await Wait(() => JobStatus(service, first) == "interrupted", "cancellation completes current reservation");
    await Wait(() => JobStatus(service, second) == "running", "next request starts after cancellation settles");
    probe.Ram = 30;
    await Wait(() => JobStatus(service, second) == "interrupted", "opening a memory-heavy app interrupts generation");
    Check(State(service).GetProperty("paused").GetBoolean(), "memory pressure pauses queue");
    var reload = new LocalAiService(root, model, probe);
    Check(State(reload).GetProperty("chats").GetArrayLength() == 2, "conversations persist across service restart");
    Check(State(reload).GetProperty("jobs").GetArrayLength() == 0, "restart never replays jobs");
    Check(File.Exists(Path.Combine(root, "workspace.json.bak")), "atomic persistence retains backup");
    var third = service.Send(service.NewChat(), "Aguardar memória");
    service.Pause(false);
    await Wait(() => State(service).GetProperty("jobs").EnumerateArray().Single(j => j.GetProperty("id").GetString() == third).GetProperty("detail").GetString().Contains("RAM"), "queued task explains resource shortage");
    service.Cancel(third); service.Pause(true);
    Check(JobStatus(service, third) == "cancelled", "queued cancellation never calls model");
    var broken = Path.Combine(root, "broken"); Directory.CreateDirectory(broken);
    var brokenFile = Path.Combine(broken, "workspace.json"); File.WriteAllText(brokenFile, "broken");
    Reject(() => new LocalAiService(broken, model, probe).GetState(), "corrupt history is not silently reset");
    Check(File.ReadAllText(brokenFile) == "broken", "corrupt source preserved");
    var interrupted = new AiLibrary(); interrupted.Chats.Add(new AiChat { Messages = new() { new AiMessage { Role = "assistant", Content = "checkpoint", Status = "running" } } });
    var checkpointStore = new AiStore(Path.Combine(root, "checkpoint")); checkpointStore.Save(interrupted);
    Check(checkpointStore.Load().Chats[0].Messages[0].Status == "interrupted", "unfinished disk checkpoints recover as interrupted");
    Check(model.MaxConcurrent == 1, "global model concurrency remains one");
    if (OperatingSystem.IsWindows())
    {
        var measured = new WindowsResourceProbe().Read();
        Console.WriteLine("Actual Windows telemetry: " + JsonSerializer.Serialize(measured, AiStore.Json));
        Check(measured.RamTotalGb > 0 && measured.RamUsedGb > 0, "Windows RAM measurement succeeds");
    }
}
finally { Directory.Delete(root, true); }
passed += await OllamaTests.Run();
passed += await RoomTests.Run();
passed += HistoryTests.Run();
passed += await AlicePanelTests.Run();
Console.WriteLine($"Local AI: {passed} checks passed.");

sealed class ScriptedHandler : HttpMessageHandler
{
    public string Response = "", LastBody = "";
    public HttpStatusCode Status = HttpStatusCode.OK;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    { LastBody = request.Content == null ? "" : await request.Content.ReadAsStringAsync(cancellationToken); return new HttpResponseMessage(Status) { Content = new StringContent(Response) }; }
}
sealed class MutableProbe : IResourceProbe
{
    public volatile int Ram = 8;
    public ResourceSnapshot Read() => new() { RamTotalGb = 32, RamUsedGb = Ram, VramTotalGb = 16, VramUsedGb = 2 };
}
sealed class FakeModel : ILocalModelClient
{
    public int Calls, Concurrent, MaxConcurrent;
    public Task<string[]> Models(AiSettings settings, CancellationToken token) => Task.FromResult(new[] { "local-test" });
    public async Task Stream(AiSettings settings, AiMessage[] messages, Action<string> append, CancellationToken token)
    {
        Interlocked.Increment(ref Calls); var count = Interlocked.Increment(ref Concurrent); MaxConcurrent = Math.Max(count, MaxConcurrent);
        try { append("parcial"); await Task.Delay(Timeout.Infinite, token); }
        finally { Interlocked.Decrement(ref Concurrent); }
    }
}
namespace Xennex.Services { public static class AppLog { public static void Error(string area, Exception error) => Console.WriteLine(area + ": " + error.Message); } }
