using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public sealed class AiRuntimeService
{
    private readonly IOllamaRuntimeClient client;
    private readonly OllamaProcessHost host;
    public AiRuntimeService(IOllamaRuntimeClient client, string modelsDirectory = null) { this.client = client; host = new(modelsDirectory); }
    public async Task<object> Detect(string savedEndpoint)
    {
        var servers = new List<object>();
        foreach (var endpoint in new[] { savedEndpoint, OllamaProcessHost.Endpoint, "http://127.0.0.1:11434/v1" }.Distinct())
        {
            try
            {
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
                var snapshot = await client.Inspect(endpoint, timeout.Token);
                servers.Add(new { snapshot.Endpoint, snapshot.Models, snapshot.CapturedAt, owned = host.Owns(endpoint) });
            }
            catch (Exception error) when (error is System.Net.Http.HttpRequestException or OperationCanceledException or System.Text.Json.JsonException or InvalidOperationException or System.Collections.Generic.KeyNotFoundException or System.IO.InvalidDataException)
            { /* An absent or incompatible local endpoint is normal during discovery. */ }
        }
        return new { installed = host.InstalledPath() != "", modelsDirectory = host.ModelsDirectory, servers };
    }
    public async Task<object> Start()
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await host.Start(client, timeout.Token);
        return await Detect(OllamaProcessHost.Endpoint);
    }
    public async Task Release(AiSettings settings)
    {
        if (settings.Provider != "ollama" || !host.Owns(settings.Endpoint))
            throw new InvalidOperationException("A liberação pelo app está disponível somente no motor iniciado pelo Xennex. Servidores externos são gerenciados no próprio motor.");
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var snapshot = await client.Inspect(settings.Endpoint, timeout.Token);
        foreach (var model in snapshot.Models.Where(m => m.Loaded))
            await client.Unload(settings.Endpoint, model.Name, timeout.Token);
    }
    public void Stop() => host.Stop();
}
