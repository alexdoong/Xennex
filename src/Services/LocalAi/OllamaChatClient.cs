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

/// <summary>Native protocol makes context, CPU mode and model residency explicit.</summary>
internal sealed class OllamaChatClient
{
    internal const string SystemPrompt = "Você é o assistente local do Xennex. Responda em português de forma útil e direta. Ajude com perguntas, cálculos, escrita e trechos de código usando o contexto da conversa. Para ações que dependem de acessar arquivos, navegar ou executar programas, forneça instruções: não há ferramentas conectadas nesta conversa. Nunca afirme ter executado uma ação externa sem um resultado de ferramenta.";
    private readonly HttpClient http;
    public OllamaChatClient(HttpClient http) { this.http = http; }
    public static void CheckContext(AiSettings settings, AiMessage[] history)
    {
        // Byte-based upper estimate, not a model tokenizer. Includes message templates and output.
        long estimate = Encoding.UTF8.GetByteCount(SystemPrompt) + 256 + settings.MaxOutputTokens;
        estimate += history.Sum(m => (long)Encoding.UTF8.GetByteCount(m.Content) + 32);
        if (estimate > settings.ContextTokens)
            throw new InvalidOperationException("A estimativa conservadora de contexto ultrapassa o limite configurado. Aumente o contexto ou abra uma conversa com um resumo; nenhuma mensagem foi descartada.");
    }
    public async Task Stream(AiSettings settings, AiMessage[] history, Action<string> append, CancellationToken token)
    {
        CheckContext(settings, history);
        var runtime = new OllamaRuntimeClient(http);
        var snapshot = await runtime.Inspect(settings.Endpoint, token);
        var model = snapshot.Models.SingleOrDefault(m => m.Name == settings.Model);
        if (model == null || model.DiskGb <= .01 || !(await runtime.Describe(settings.Endpoint, settings.Model, token)).LocalCompletion)
            throw new InvalidOperationException("Selecione um modelo de conversa com pesos locais. Modelos remotos não são usados nesta integração.");
        var messages = LocalModelClient.ModelMessages(history);
        var options = new Dictionary<string, object> { ["num_ctx"] = settings.ContextTokens, ["num_predict"] = settings.MaxOutputTokens };
        if (!settings.UseGpu) options["num_gpu"] = 0;
        using var request = LocalHttp.Post(LocalHttp.OllamaUri(settings.Endpoint, "chat"), new { model = settings.Model, messages, options, think = false, stream = true, keep_alive = settings.KeepAliveSeconds });
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        LocalHttp.EnsureSuccess(response);
        using var stream = await response.Content.ReadAsStreamAsync(token);
        using var reader = new StreamReader(stream);
        int length = 0;
        while (true)
        {
            var line = await LocalHttp.Line(reader, token);
            if (line == null) throw new IOException("O Ollama encerrou a resposta antes de confirmar a conclusão.");
            if (string.IsNullOrWhiteSpace(line)) continue;
            using var data = JsonDocument.Parse(line);
            var root = data.RootElement;
            if (root.TryGetProperty("error", out _)) throw new IOException("O Ollama informou uma falha durante a resposta.");
            if (root.TryGetProperty("message", out var message) && message.TryGetProperty("content", out var content) && content.ValueKind == JsonValueKind.String)
            {
                var chunk = content.GetString(); length += chunk.Length;
                if (length > 64000) throw new InvalidDataException("Resposta acima de 64 mil caracteres. Reduza a saída.");
                if (chunk.Length > 0) append(chunk);
            }
            if (root.TryGetProperty("done", out var done) && done.ValueKind == JsonValueKind.True) return;
        }
    }
}
