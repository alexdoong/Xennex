using System;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public interface IOllamaRuntimeClient
{
    Task<OllamaSnapshot> Inspect(string endpoint, CancellationToken token);
    Task<OllamaModelInfo> Describe(string endpoint, string model, CancellationToken token);
    Task Unload(string endpoint, string model, CancellationToken token);
}
public sealed class OllamaRuntimeClient : IOllamaRuntimeClient
{
    private readonly HttpClient http;
    public OllamaRuntimeClient(HttpMessageHandler handler = null) { http = LocalHttp.Create(handler); }
    internal OllamaRuntimeClient(HttpClient http) { this.http = http; }
    public async Task<OllamaSnapshot> Inspect(string endpoint, CancellationToken token)
    {
        using var tagsRequest = new HttpRequestMessage(HttpMethod.Get, LocalHttp.OllamaUri(endpoint, "tags"));
        using var tags = await LocalHttp.Json(http, tagsRequest, token);
        using var psRequest = new HttpRequestMessage(HttpMethod.Get, LocalHttp.OllamaUri(endpoint, "ps"));
        using var ps = await LocalHttp.Json(http, psRequest, token);
        var snapshot = new OllamaSnapshot { Endpoint = endpoint };
        var loaded = ps.RootElement.GetProperty("models").EnumerateArray().ToArray();
        foreach (var item in tags.RootElement.GetProperty("models").EnumerateArray().Take(200))
        {
            string name = Text(item, "name");
            if (name.Length == 0 || name.Length > 200) continue;
            var model = new OllamaModel { Name = name, Digest = Text(item, "digest"), DiskGb = Number(item, "size") / 1073741824.0 };
            var resident = loaded.FirstOrDefault(m => Text(m, "name") == name && Text(m, "digest") == model.Digest);
            if (resident.ValueKind == JsonValueKind.Object)
            {
                model.PlacementKnown = resident.TryGetProperty("size_vram", out var vram) && vram.ValueKind == JsonValueKind.Number && vram.TryGetDouble(out var sizeVram) && double.IsFinite(sizeVram) && sizeVram >= 0;
                model.Loaded = true; model.LoadedGb = Number(resident, "size") / 1073741824.0;
                model.LoadedVramGb = Number(resident, "size_vram") / 1073741824.0;
                model.LoadedContext = (int)Math.Min(1000000, Number(resident, "context_length"));
            }
            snapshot.Models.Add(model);
        }
        return snapshot;
    }
    public async Task<OllamaModelInfo> Describe(string endpoint, string model, CancellationToken token)
    {
        using var request = LocalHttp.Post(LocalHttp.OllamaUri(endpoint, "show"), new { model });
        using var json = await LocalHttp.Json(http, request, token);
        var root = json.RootElement;
        var result = new OllamaModelInfo { LocalCompletion = Text(root, "remote_host") == "" && Text(root, "remote_model") == "" };
        if (root.TryGetProperty("capabilities", out var capabilities)) result.LocalCompletion &= capabilities.EnumerateArray().Any(c => c.GetString() == "completion");
        if (root.TryGetProperty("model_info", out var info))
        {
            var architecture = Text(info, "general.architecture");
            double layers = Number(info, architecture + ".block_count"), heads = Number(info, architecture + ".attention.head_count");
            double kvHeads = Number(info, architecture + ".attention.head_count_kv"), embedding = Number(info, architecture + ".embedding_length");
            double key = Number(info, architecture + ".attention.key_length"), value = Number(info, architecture + ".attention.value_length");
            if (key == 0 && heads > 0) key = embedding / heads;
            if (value == 0) value = key;
            double bytes = layers * kvHeads * (key + value) * 2; // Conservative f16 KV estimate; not model weights.
            if (bytes > 0 && bytes < 100000000) result.CacheBytesPerToken = bytes;
        }
        return result;
    }
    public async Task Unload(string endpoint, string model, CancellationToken token)
    {
        using var request = LocalHttp.Post(LocalHttp.OllamaUri(endpoint, "generate"), new { model, keep_alive = 0, stream = false });
        using var response = await LocalHttp.Json(http, request, token);
    }
    private static string Text(JsonElement element, string key) => element.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
    private static double Number(JsonElement element, string key)
    {
        if (!element.TryGetProperty(key, out var value) || value.ValueKind != JsonValueKind.Number || !value.TryGetDouble(out var number) || !double.IsFinite(number) || number < 0) return 0;
        return number;
    }
}
