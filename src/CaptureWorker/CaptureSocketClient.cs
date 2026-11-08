using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Xennex.CaptureWorker;

internal sealed class CaptureSocketClient(WebSocket socket, Func<string> status, Action<string> log, Func<string>? metrics = null) : IDisposable
{
    private byte[]? pending;
    private int sending;
    private volatile string lastStatus = "";
    private volatile string lastMetrics = "";
    private volatile bool disposed;
    internal WebSocket Socket => socket;

    internal void QueueFrame(byte[]? frame)
    {
        if (disposed) return;
        if (frame != null) Interlocked.Exchange(ref pending, frame);
        Schedule();
    }
    private bool HasWork() => Volatile.Read(ref pending) != null || (status().Length > 0 && status() != lastStatus) ||
        (metrics is not null && metrics().Length > 0 && metrics() != lastMetrics);
    private void Schedule()
    {
        if (disposed || socket.State != WebSocketState.Open || !HasWork() || Interlocked.CompareExchange(ref sending, 1, 0) != 0) return;
        _ = Task.Run(Drain);
    }
    private async Task Drain()
    {
        try
        {
            while (!disposed && socket.State == WebSocketState.Open)
            {
                string currentStatus = status();
                if (currentStatus.Length > 0 && lastStatus != currentStatus)
                {
                    var message = Encoding.UTF8.GetBytes("{\"type\":\"capture-status\",\"phase\":\"" + currentStatus + "\"}");
                    await socket.SendAsync(new ArraySegment<byte>(message), WebSocketMessageType.Text, true, CancellationToken.None);
                    lastStatus = currentStatus;
                }
                byte[]? frame = Interlocked.Exchange(ref pending, null);
                if (frame != null) await socket.SendAsync(new ArraySegment<byte>(frame), WebSocketMessageType.Binary, true, CancellationToken.None);
                // Measurements follow the image and share the same serialized sender.
                string currentMetrics = metrics?.Invoke() ?? "";
                if (currentMetrics.Length > 0 && currentMetrics != lastMetrics)
                {
                    await socket.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(currentMetrics)), WebSocketMessageType.Text, true, CancellationToken.None);
                    lastMetrics = currentMetrics;
                }
                if (!HasWork()) break;
            }
        }
        catch (Exception ex)
        {
            log($"Erro ao transmitir captura: {ex.Message}");
            Dispose();
        }
        finally
        {
            Interlocked.Exchange(ref sending, 0);
            Schedule(); // Cover a new frame arriving between the final check and releasing the sender.
        }
    }
    public void Dispose()
    {
        if (disposed) return;
        disposed = true; Interlocked.Exchange(ref pending, null); socket.Dispose();
    }
}
