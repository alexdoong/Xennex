using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Xennex.Services.LocalAi;

internal static class LocalHttp
{
    public static HttpClient Create(HttpMessageHandler handler = null) => new(handler ?? new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false }) { Timeout = Timeout.InfiniteTimeSpan };
    public static Uri OllamaUri(string endpoint, string route) => new(LocalModelClient.Endpoint(endpoint), "../api/" + route);
    public static async Task<JsonDocument> Json(HttpClient http, HttpRequestMessage request, CancellationToken token)
    {
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        EnsureSuccess(response);
        using var stream = await response.Content.ReadAsStreamAsync(token);
        using var reader = new StreamReader(stream);
        var buffer = new char[1024 * 1024 + 1]; int count = 0, read;
        while (count < buffer.Length && (read = await reader.ReadAsync(buffer.AsMemory(count), token)) > 0) count += read;
        if (count == buffer.Length) throw new InvalidDataException("Resposta de metadados acima de 1 MiB.");
        return JsonDocument.Parse(new string(buffer, 0, count));
    }
    public static HttpRequestMessage Post(Uri uri, object body) => new(HttpMethod.Post, uri) { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
    public static void EnsureSuccess(HttpResponseMessage response)
    {
        if (!response.IsSuccessStatusCode) throw new HttpRequestException($"Motor local retornou HTTP {(int)response.StatusCode}. Confira a conexão e o modelo instalado.");
    }
    public static async Task<string> Line(StreamReader reader, CancellationToken token)
    {
        var line = new StringBuilder(); var one = new char[1];
        while (await reader.ReadAsync(one.AsMemory(), token) > 0)
        {
            if (one[0] == '\n') return line.ToString().TrimEnd('\r');
            line.Append(one[0]);
            if (line.Length > 128 * 1024) throw new InvalidDataException("Evento do motor local acima do limite.");
        }
        return line.Length == 0 ? null : line.ToString();
    }
}
