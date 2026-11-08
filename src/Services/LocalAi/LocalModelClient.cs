using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public interface ILocalModelClient
{
    Task<string[]> Models(AiSettings settings, CancellationToken token);
    Task Stream(AiSettings settings, AiMessage[] history, Action<string> append, CancellationToken token);
}

public sealed class LocalModelClient : ILocalModelClient
{
    private readonly HttpClient http;
    private readonly OllamaChatClient ollama;
    public LocalModelClient(HttpMessageHandler handler = null)
    {
        http = new HttpClient(handler ?? new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        http.Timeout = Timeout.InfiniteTimeSpan;
        ollama = new OllamaChatClient(http);
    }
    public static Uri Endpoint(string value)
    {
        if (!Uri.TryCreate(value?.Trim(), UriKind.Absolute, out var uri) || uri.Scheme != "http" ||
            uri.UserInfo != "" || uri.Query != "" || uri.Fragment != "" ||
            (uri.Host != "127.0.0.1" && uri.Host != "[::1]" && uri.Host != "::1") || uri.AbsolutePath.TrimEnd('/') != "/v1")
            throw new ArgumentException("Use um servidor local: http://127.0.0.1:1234/v1 (ou [::1]). Destinos externos não são aceitos.");
        return new Uri(uri.AbsoluteUri.TrimEnd('/') + "/");
    }
    public static void ValidateSettings(AiSettings settings)
    {
        if (settings == null) throw new ArgumentException("Configuração ausente.");
        Endpoint(settings.Endpoint);
        if (settings.Provider is not ("compatible" or "ollama") || (settings.AutoBudget && settings.Provider != "ollama") ||
            settings.ContextTokens < 2048 || settings.ContextTokens > 16384 || settings.KeepAliveSeconds < 0 || settings.KeepAliveSeconds > 300 ||
            (settings.Provider == "ollama" && settings.MaxOutputTokens + 512 >= settings.ContextTokens))
            throw new ArgumentException("Confira o provedor, contexto (2048–16384 tokens) e permanência (0–300 segundos). Reserve contexto para a entrada.");
        if (settings.Model == null || settings.Model.Length > 200 || settings.MemoryLimitPercent < 50 || settings.MemoryLimitPercent > 85 ||
            !double.IsFinite(settings.AdditionalRamGb) || settings.AdditionalRamGb < .25 || settings.AdditionalRamGb > 256 ||
            !double.IsFinite(settings.AdditionalVramGb) || settings.AdditionalVramGb < .25 || settings.AdditionalVramGb > 256 ||
            settings.MaxOutputTokens < 128 || settings.MaxOutputTokens > 4096)
            throw new ArgumentException("Confira o orçamento (50–85%), reservas (0,25–256 GiB) e saída (128–4096 tokens).");
    }
    public async Task<string[]> Models(AiSettings settings, CancellationToken token)
    {
        if (settings.Provider == "ollama") return (await new OllamaRuntimeClient(http).Inspect(settings.Endpoint, token)).Models.Select(m => m.Name).ToArray();
        using var response = await http.GetAsync(new Uri(Endpoint(settings.Endpoint), "models"), HttpCompletionOption.ResponseHeadersRead, token);
        await EnsureSuccess(response);
        using var body = await response.Content.ReadAsStreamAsync(token);
        using var reader = new StreamReader(body);
        var buffer = new char[128 * 1024 + 1];
        int count = 0, read;
        while (count < buffer.Length && (read = await reader.ReadAsync(buffer.AsMemory(count), token)) > 0) count += read;
        if (count == buffer.Length) throw new InvalidDataException("Catálogo local acima do limite de tamanho.");
        using var json = JsonDocument.Parse(new string(buffer, 0, count));
        return json.RootElement.GetProperty("data").EnumerateArray().Select(m => m.GetProperty("id").GetString())
            .Where(m => !string.IsNullOrWhiteSpace(m) && m.Length <= 200).Distinct().Take(200).ToArray();
    }
    public async Task Stream(AiSettings settings, AiMessage[] history, Action<string> append, CancellationToken token)
    {
        if (settings.Provider == "ollama") { await ollama.Stream(settings, history, append, token); return; }
        var messages = ModelMessages(history);
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(Endpoint(settings.Endpoint), "chat/completions"));
        request.Content = new StringContent(JsonSerializer.Serialize(new { model = settings.Model, messages, stream = true, max_tokens = settings.MaxOutputTokens }), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        await EnsureSuccess(response);
        using var stream = await response.Content.ReadAsStreamAsync(token);
        using var reader = new StreamReader(stream);
        int outputLength = 0;
        while (true)
        {
            var line = await ReadLineBounded(reader, token);
            if (line == null) throw new IOException("O servidor encerrou a resposta antes da confirmação de conclusão.");
            if (!line.StartsWith("data:", StringComparison.Ordinal)) continue;
            var payload = line.Substring(5).Trim();
            if (payload == "[DONE]") return;
            if (payload.Length == 0) continue;
            using var data = JsonDocument.Parse(payload);
            if (data.RootElement.TryGetProperty("error", out _)) throw new IOException("O modelo local informou uma falha durante a resposta.");
            if (!data.RootElement.TryGetProperty("choices", out var choices)) continue;
            foreach (var choice in choices.EnumerateArray())
            {
                if (!choice.TryGetProperty("delta", out var delta) || !delta.TryGetProperty("content", out var content) || content.ValueKind != JsonValueKind.String) continue;
                var chunk = content.GetString();
                outputLength += chunk.Length;
                if (outputLength > 64000) throw new InvalidDataException("Resposta acima de 64 mil caracteres. Reduza a saída.");
                append(chunk);
            }
        }
    }
    internal static List<object> ModelMessages(AiMessage[] history)
    {
        // Many local chat templates only support one system message.
        string system = OllamaChatClient.SystemPrompt + "\n" + string.Join("\n", history.Where(m => m.Role == "system").Select(m => m.Content));
        var messages = new List<object> { new { role = "system", content = system } };
        messages.AddRange(history.Where(m => m.Role != "system").Select(m => (object)new { role = m.Role, content = m.Content }));
        return messages;
    }
    private static async Task<string> ReadLineBounded(StreamReader reader, CancellationToken token)
    {
        var line = new StringBuilder();
        var one = new char[1];
        while (await reader.ReadAsync(one.AsMemory(), token) > 0)
        {
            if (one[0] == '\n') return line.ToString().TrimEnd('\r');
            line.Append(one[0]);
            if (line.Length > 128 * 1024) throw new InvalidDataException("Evento do servidor local acima do limite.");
        }
        return line.Length == 0 ? null : line.ToString();
    }
    private static Task EnsureSuccess(HttpResponseMessage response)
    {
        if (response.IsSuccessStatusCode) return Task.CompletedTask;
        throw new HttpRequestException($"Servidor local retornou HTTP {(int)response.StatusCode}. Confira o motor, o modelo carregado e a configuração de autenticação.");
    }
}
