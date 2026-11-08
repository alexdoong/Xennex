using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

/// <summary>Serial job coordinator; UI polling never owns a model request.</summary>
public sealed partial class LocalAiService
{
    private readonly object sync = new();
    private readonly AiStore store;
    private readonly ILocalModelClient client;
    private readonly IResourceProbe probe;
    private readonly IOllamaRuntimeClient ollama;
    private readonly AiRuntimeService runtime;
    private bool runtimeChanging;
    private AiLibrary library;
    private readonly List<AiJob> jobs = new();
    private ResourceSnapshot resources = new() { CapturedAt = DateTimeOffset.MinValue };
    private CancellationTokenSource activeCancellation;
    private bool workerRunning, paused;
    private string warning = "";
    private DateTimeOffset lastCheckpoint;

    public LocalAiService(string directory = null, ILocalModelClient client = null, IResourceProbe probe = null, IOllamaRuntimeClient ollama = null)
    {
        store = new AiStore(directory ?? Path.Combine(AppContext.BaseDirectory, "Data", "ai"));
        this.client = client ?? new LocalModelClient();
        this.probe = probe ?? new WindowsResourceProbe();
        this.ollama = ollama ?? new OllamaRuntimeClient();
        runtime = new AiRuntimeService(this.ollama, Path.Combine(directory ?? Path.Combine(AppContext.BaseDirectory, "Data", "ai"), "models"));
    }
    private void EnsureLoaded() { library ??= store.Load(); }
    private static T Copy<T>(T value) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(value, AiStore.Json), AiStore.Json);
    private bool Busy => jobs.Any(j => j.Status is "queued" or "running");
    private void Commit(AiLibrary next) { store.Save(next); library = next; }
    public string GetState()
    {
        lock (sync)
        {
            EnsureLoaded();
            return JsonSerializer.Serialize(new { settings = library.Settings, chats = library.Chats, specialists = library.Specialists, jobs, resources, paused, warning }, AiStore.Json);
        }
    }
    public async Task<string> RefreshResources()
    {
        var snapshot = await Task.Run(probe.Read);
        lock (sync) { resources = snapshot; return JsonSerializer.Serialize(snapshot, AiStore.Json); }
    }
    public string SaveSettings(string json)
    {
        lock (sync)
        {
            EnsureLoaded();
            if (Busy || runtimeChanging) throw new InvalidOperationException("Cancele ou conclua a fila antes de alterar as configurações.");
            if (json == null || json.Length > 8192) throw new ArgumentException("Configuração inválida.");
            var settings = JsonSerializer.Deserialize<AiSettings>(json, AiStore.Json);
            LocalModelClient.ValidateSettings(settings);
            var next = Copy(library); next.Settings = settings; Commit(next);
            return GetState();
        }
    }
    public async Task<string> DiscoverModels()
    {
        AiSettings settings;
        lock (sync) { EnsureLoaded(); settings = Copy(library.Settings); }
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            return JsonSerializer.Serialize(await client.Models(settings, timeout.Token));
        }
        catch (Exception error) { AppLog.Error("LocalAi.Models", error); throw new InvalidOperationException("Não foi possível consultar o motor local. Inicie seu servidor e confira o endereço salvo. " + error.Message); }
    }
    public async Task<string> DetectRuntime()
    {
        string endpoint;
        lock (sync) { EnsureLoaded(); endpoint = library.Settings.Endpoint; }
        return JsonSerializer.Serialize(await runtime.Detect(endpoint), AiStore.Json);
    }
    public Task<string> StartRuntime() => ChangeRuntime(true);
    public Task<string> ReleaseModel() => ChangeRuntime(false);
    private async Task<string> ChangeRuntime(bool start)
    {
        AiSettings settings;
        lock (sync)
        {
            EnsureLoaded();
            if (Busy || runtimeChanging) throw new InvalidOperationException("Conclua ou cancele a fila antes de gerenciar o motor.");
            runtimeChanging = true; settings = Copy(library.Settings);
        }
        try
        {
            if (start) return JsonSerializer.Serialize(await runtime.Start(), AiStore.Json);
            await runtime.Release(settings);
            await RefreshResources();
            return await DetectRuntime();
        }
        catch (Exception error) { AppLog.Error("LocalAi.Runtime", error); throw; }
        finally { lock (sync) runtimeChanging = false; }
    }
    public string NewChat()
    {
        lock (sync)
        {
            EnsureLoaded();
            if (library.Chats.Count >= 100) throw new InvalidOperationException("Limite de 100 conversas. Exporte e remova conversas antigas.");
            var next = Copy(library); var chat = new AiChat(); next.Chats.Insert(0, chat); Commit(next);
            return chat.Id;
        }
    }
    public void DeleteChat(string id)
    {
        lock (sync)
        {
            EnsureLoaded();
            if (jobs.Any(j => j.ChatId == id && j.Status is "queued" or "running")) throw new InvalidOperationException("Cancele a tarefa desta conversa antes de removê-la.");
            var next = Copy(library); next.Chats.RemoveAll(c => c.Id == id); Commit(next);
            jobs.RemoveAll(j => j.ChatId == id);
        }
    }
    public string Send(string id, string text)
    {
        lock (sync)
        {
            EnsureLoaded();
            if (runtimeChanging) throw new InvalidOperationException("Aguarde o gerenciamento do motor terminar.");
            if (string.IsNullOrWhiteSpace(text) || text.Length > 16000) throw new ArgumentException("Escreva de 1 a 16 mil caracteres.");
            if (string.IsNullOrWhiteSpace(library.Settings.Model)) throw new InvalidOperationException("Escolha e salve um modelo local em Conexão e orçamento.");
            if (jobs.Count(j => j.Status is "queued" or "running") >= 20) throw new InvalidOperationException("A fila já tem 20 tarefas.");
            if (jobs.Any(j => j.ChatId == id && j.Status is "queued" or "running")) throw new InvalidOperationException("Esta conversa já tem uma tarefa em andamento.");
            var next = Copy(library);
            var chat = next.Chats.SingleOrDefault(c => c.Id == id) ?? throw new ArgumentException("Conversa não encontrada.");
            if (chat.Project != null) throw new InvalidOperationException("Use os controles da sala para selecionar os especialistas.");
            if (chat.Messages.Count >= 198) throw new InvalidOperationException("Abra uma nova conversa; esta atingiu o limite de mensagens.");
            // Explicit context bound; never silently drop the beginning of the conversation.
            if (chat.Messages.Where(m => m.Status == "complete").Sum(m => m.Content.Length) + text.Length > 24000)
                throw new InvalidOperationException("Contexto acima de 24 mil caracteres. Abra uma nova conversa com um resumo. O limite real de tokens depende do modelo.");
            if (next.Settings.Provider == "ollama") OllamaChatClient.CheckContext(next.Settings, chat.Messages.Where(m => m.Status == "complete").Append(new AiMessage { Content = text }).ToArray());
            if (chat.Messages.Count == 0) chat.Title = text.Trim().Substring(0, Math.Min(text.Trim().Length, 64));
            chat.Model = next.Settings.Model; chat.UpdatedAt = DateTimeOffset.UtcNow;
            chat.Messages.Add(new AiMessage { Role = "user", Content = text.Trim() });
            chat.Messages.Add(new AiMessage { Role = "assistant", Status = "queued" });
            Commit(next);
            var job = new AiJob { ChatId = id, MessageId = chat.Messages.Last().Id, Settings = Copy(library.Settings) };
            jobs.Add(job);
            TrimJobs();
            StartWorker(); return job.Id;
        }
    }
    public void Stop()
    {
        lock (sync)
        {
            paused = true;
            runtime.Stop();
            activeCancellation?.Cancel();
            if (library == null) return;
            try { store.Save(library); }
            catch (Exception error) { AppLog.Error("LocalAi.Stop", error); }
        }
    }
    public void Pause(bool value)
    {
        lock (sync)
        {
            paused = value;
            if (value && activeCancellation != null)
            {
                var active = jobs.FirstOrDefault(j => j.Status == "running");
                if (active != null) active.Detail = "Interrompido para priorizar o uso do PC. A fila está pausada.";
                activeCancellation.Cancel();
            }
            if (!value) StartWorker();
        }
    }
    public void Cancel(string id)
    {
        lock (sync)
        {
            var job = jobs.FirstOrDefault(j => j.Id == id);
            if (job == null || job.Status is not ("queued" or "running")) return;
            job.Detail = "Cancelado por você; conteúdo parcial preservado.";
            var active = jobs.FirstOrDefault(j => job.RunId != "" && j.RunId == job.RunId && j.Status == "running");
            if (active != null) { active.Detail = job.Detail; activeCancellation?.Cancel(); }
            if (job.Status == "running") { activeCancellation?.Cancel(); return; }
            Complete(job, "cancelled");
        }
    }
    private void StartWorker()
    {
        if (workerRunning || paused || !jobs.Any(j => j.Status == "queued")) return;
        workerRunning = true;
        _ = Task.Run(RunQueue);
    }
    private async Task RunQueue()
    {
        try
        {
            while (true)
            {
                AiJob job;
                lock (sync)
                {
                    if (paused) return;
                    job = jobs.FirstOrDefault(j => j.Status == "queued");
                    if (job == null) return;
                }
                ResourceDemand demand;
                try { demand = await PlanResources(job.Settings); }
                catch (Exception error)
                {
                    AppLog.Error("LocalAi.Estimate", error);
                    lock (sync)
                    {
                        if (job.Status == "queued") { job.Detail = "Não foi possível preparar o modelo: " + error.Message; Complete(job, "failed"); }
                    }
                    continue;
                }
                var snapshot = probe.Read(); AiMessage[] history;
                lock (sync)
                {
                    resources = snapshot;
                    if (paused) return;
                    if (job.Status != "queued") continue;
                    job.Demand = demand;
                    var admission = Copy(job.Settings);
                    admission.AdditionalRamGb = demand.RamGb; admission.AdditionalVramGb = demand.VramGb;
                    var reason = ResourcePolicy.Check(resources, admission, true);
                    if (reason != "") { job.Detail = reason; history = null; }
                    else
                    {
                        try { history = PrepareHistory(job); }
                        catch (Exception error)
                        {
                            AppLog.Error("LocalAi.Context",error); job.Detail = error.Message; Complete(job,"failed"); continue;
                        }
                        job.Status = "running"; job.Detail = "Recebendo resposta do modelo local"; job.StartedAt = DateTimeOffset.UtcNow;
                        Message(job).Status = "running";
                        activeCancellation = new CancellationTokenSource(TimeSpan.FromMinutes(10));
                    }
                }
                if (history == null) { await Task.Delay(2000); continue; }
                await Execute(job, history);
            }
        }
        catch (Exception error)
        {
            AppLog.Error("LocalAi.Queue", error);
            lock (sync) { paused = true; warning = "A fila foi pausada por uma falha: " + error.Message; }
        }
        finally { lock (sync) { workerRunning = false; StartWorker(); } }
    }
    private async Task<ResourceDemand> PlanResources(AiSettings settings)
    {
        if (!settings.AutoBudget) return ModelMemoryEstimator.Manual(settings);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        var snapshot = await ollama.Inspect(settings.Endpoint, timeout.Token);
        var info = await ollama.Describe(settings.Endpoint, settings.Model, timeout.Token);
        lock (sync) return ModelMemoryEstimator.Estimate(settings, snapshot.Models.FirstOrDefault(m => m.Name == settings.Model), info, library.Measurements);
    }
    private async Task Execute(AiJob job, AiMessage[] history)
    {
        CancellationTokenSource cancellation;
        lock (sync) cancellation = activeCancellation;
        using var monitorStop = new CancellationTokenSource();
        JobMemoryObservation observation;
        lock (sync) observation = new JobMemoryObservation(resources);
        var monitor = Monitor(job, observation, cancellation, monitorStop.Token);
        string status = "complete";
        try
        {
            await client.Stream(job.Settings, history, chunk =>
            {
                lock (sync)
                {
                    cancellation.Token.ThrowIfCancellationRequested();
                    Message(job).Content += chunk;
                    if (DateTimeOffset.UtcNow - lastCheckpoint > TimeSpan.FromSeconds(3))
                    { store.Save(library); lastCheckpoint = DateTimeOffset.UtcNow; }
                }
            }, cancellation.Token);
            cancellation.Token.ThrowIfCancellationRequested();
            lock (sync) job.Detail = "Resposta concluída";
        }
        catch (OperationCanceledException)
        {
            status = "interrupted";
            lock (sync) if (job.Detail == "Recebendo resposta do modelo local") job.Detail = "Tempo máximo de 10 minutos atingido; resposta parcial preservada.";
        }
        catch (Exception error)
        {
            AppLog.Error("LocalAi.Response", error); status = "failed";
            lock (sync) job.Detail = "Falha no modelo local: " + error.Message;
        }
        finally
        {
            monitorStop.Cancel();
            await monitor;
            try { observation.Sample(probe.Read()); }
            catch (Exception error) { AppLog.Error("LocalAi.Measurement", error); }
            lock (sync)
            {
                if (status is "complete" or "interrupted") ModelMemoryEstimator.Observe(library.Measurements, job.Demand, observation.Ram, observation.Vram);
                if (job.RunId != "")
                {
                    var run = Project(FindChat(library,job.ChatId)).Runs.Single(r => r.Id == job.RunId);
                    run.ObservedRamGb = Math.Max(run.ObservedRamGb,observation.Ram);
                    run.ObservedVramGb = Math.Max(run.ObservedVramGb,observation.Vram);
                }
                Complete(job, status); activeCancellation = null; cancellation.Dispose();
            }
        }
    }
    private async Task Monitor(AiJob job, JobMemoryObservation observation, CancellationTokenSource cancellation, CancellationToken stop)
    {
        try
        {
            while (true)
            {
                await Task.Delay(1500, stop);
                var snapshot = probe.Read();
                lock (sync)
                {
                    resources = snapshot; observation.Sample(snapshot);
                    var reason = ResourcePolicy.Check(snapshot, job.Settings, false);
                    if (reason == "") continue;
                    paused = true; job.Detail = "Proteção de memória: " + reason + " A fila foi pausada.";
                    cancellation.Cancel(); return;
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception error)
        {
            AppLog.Error("LocalAi.Monitor", error);
            lock (sync) { paused = true; job.Detail = "Telemetria falhou; fila pausada."; cancellation.Cancel(); }
        }
    }
    private void Complete(AiJob job, string status)
    {
        job.Status = status;
        var chat = library.Chats.Single(c => c.Id == job.ChatId);
        var message = Message(job); message.Status = status; message.Detail = job.Detail;
        FinishRoomTurn(job,status);
        chat.UpdatedAt = DateTimeOffset.UtcNow;
        try { store.Save(library); warning = ""; }
        catch (Exception error) { paused = true; warning = "Falha ao salvar o histórico. Exporte a conversa antes de fechar: " + error.Message; }
    }
}
