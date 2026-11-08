using System;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.Assets;
using Xennex.Services.Assets;

namespace Xennex.Services.Vr;

public sealed class AssetVrService : IDisposable
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };
    private readonly object _gate = new();
    private readonly Func<string, AssetItem> _resolve;
    private readonly Func<string, Stream> _open;
    private readonly Func<IVrOverlay> _createOverlay;
    private readonly Func<VrGallerySession, Func<string, Stream>, byte[]> _render;
    private readonly Func<AssetQuery, AssetPage> _query;
    private readonly Func<System.Collections.Generic.IReadOnlyList<AssetRoot>> _roots;
    private readonly ConcurrentQueue<string> _commands = new();
    private CancellationTokenSource _cancel;
    private Task _worker;
    private AssetVrState _state = new();
    private bool _disposed;

    public AssetVrService(AssetLibraryService assets) : this(
        id => JsonSerializer.Deserialize<AssetItem>(assets.GetDetails(id), Json),
        id => assets.OpenMedia(id, "preview").content, () => new OpenVrOverlay(),
        (session, open) => VrPanelRenderer.Render(session, open, id => assets.OpenMedia(id, "thumb").content),
        query => JsonSerializer.Deserialize<AssetPage>(assets.Query(JsonSerializer.Serialize(query, Json)), Json),
        () => JsonSerializer.Deserialize<System.Collections.Generic.List<AssetRoot>>(assets.GetRoots(), Json)) { }

    internal AssetVrService(Func<string, AssetItem> resolve, Func<string, Stream> open,
        Func<IVrOverlay> createOverlay, Func<VrGallerySession, Func<string, Stream>, byte[]> render,
        Func<AssetQuery, AssetPage> query = null, Func<System.Collections.Generic.IReadOnlyList<AssetRoot>> roots = null)
    { _resolve = resolve; _open = open; _createOverlay = createOverlay; _render = render; _query = query; _roots = roots; }

    public Task<string> Start(string json)
    {
        if (string.IsNullOrWhiteSpace(json) || json.Length > 16384) throw new ArgumentException("Seleção VR inválida.");
        var request = JsonSerializer.Deserialize<AssetVrRequest>(json, Json) ?? throw new ArgumentException("Seleção VR inválida.");
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_worker != null && !_worker.IsCompleted) throw new InvalidOperationException("Encerre o painel VR atual antes de abrir outra seleção.");
            _cancel?.Dispose();
            _cancel = new CancellationTokenSource();
            _commands.Clear();
            _state = new AssetVrState { State = "starting" };
            var ready = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
            var token = _cancel.Token;
            _worker = Task.Factory.StartNew(() => Run(request, token, ready), CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
            return ready.Task;
        }
    }

    public string GetState() { lock (_gate) return JsonSerializer.Serialize(_state, Json); }

    public void Control(string action)
    {
        if (!VrGallerySession.IsAction(action)) throw new ArgumentException("Comando VR inválido.");
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_state.State != "running") throw new InvalidOperationException("O painel VR não está aberto.");
            if (_commands.Count >= 64) throw new InvalidOperationException("Aguarde o painel VR processar os comandos anteriores.");
            _commands.Enqueue(action);
        }
    }

    private void Run(AssetVrRequest request, CancellationToken token, TaskCompletionSource<string> ready)
    {
        VrGallerySession session = null;
        try
        {
            session = new VrGallerySession(request, _resolve, _query, _roots, token.ThrowIfCancellationRequested);
            token.ThrowIfCancellationRequested();
            using var overlay = _createOverlay();
            overlay.Connect();
            token.ThrowIfCancellationRequested();
            overlay.Present(_render(session, _open));
            token.ThrowIfCancellationRequested();
            SetState(session.Snapshot("running"));
            ready.TrySetResult(GetState());
            while (!token.IsCancellationRequested)
            {
                var actions = overlay.PollActions((x, y) => VrPanelLayout.Hit(session, x, y)).Take(128).ToList();
                while (actions.Count < 192 && _commands.TryDequeue(out var command)) actions.Add(command);
                if (actions.Contains("close")) break;
                if (actions.Count > 0)
                {
                    foreach (var action in actions)
                    {
                        session.Apply(action);
                        if (action == "pin") overlay.SetPinned(session.Pinned);
                        if (action == "recenter") overlay.Recenter();
                        if (action is "sizeUp" or "sizeDown" or "nearer" or "farther") overlay.SetSize(session.WidthMeters, session.DistanceMeters);
                    }
                    token.ThrowIfCancellationRequested();
                    overlay.Present(_render(session, _open));
                    SetState(session.Snapshot("running"));
                }
                token.WaitHandle.WaitOne(25);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { ready.TrySetCanceled(token); }
        catch (Exception error)
        {
            AppLog.Error("VR gallery", error);
            SetState(session?.Snapshot("failed", error.Message) ?? new AssetVrState { State = "failed", Error = error.Message });
            ready.TrySetException(error);
        }
        finally
        {
            lock (_gate)
                if (_state.State != "failed") _state = session?.Snapshot("stopped") ?? new AssetVrState();
            ready.TrySetCanceled();
        }
    }

    private void SetState(AssetVrState state) { lock (_gate) _state = state; }

    public async Task Stop()
    {
        Task worker;
        lock (_gate) { _cancel?.Cancel(); worker = _worker; }
        if (worker != null) await worker.ConfigureAwait(false);
    }

    public void Dispose()
    {
        lock (_gate)
        {
            if (_disposed) return;
            _disposed = true;
            var cancel = _cancel;
            _cancel = null;
            cancel?.Cancel();
            if (_worker == null) { cancel?.Dispose(); return; }
            _ = _worker.ContinueWith(_ => cancel?.Dispose(), TaskScheduler.Default);
        }
    }
}
