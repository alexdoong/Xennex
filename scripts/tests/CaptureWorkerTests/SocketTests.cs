using System.Collections.Concurrent;
using System.Net.WebSockets;
using Xennex.CaptureWorker;

internal static class SocketTests
{
    internal static async Task Run()
    {
        string status = "recovering";
        using var socket = new SlowSocket();
        using var sender = new CaptureSocketClient(socket, () => status, message => throw new Exception(message));
        sender.QueueFrame(null);
        await socket.Started.Task.WaitAsync(TimeSpan.FromSeconds(3));
        for (byte value = 1; value <= 10; value++) sender.QueueFrame(new[] { value });
        status = "ready"; sender.QueueFrame(null); socket.Release.TrySetResult();
        var deadline = DateTime.UtcNow.AddSeconds(3);
        while (socket.Messages.Count < 3 && DateTime.UtcNow < deadline) await Task.Delay(5);
        var messages = socket.Messages.ToArray();
        if (messages.Length != 3 || messages.Count(item => item.Type == WebSocketMessageType.Binary) != 1 ||
            messages.Single(item => item.Type == WebSocketMessageType.Binary).Bytes[0] != 10 || socket.MaximumConcurrent > 1)
            throw new Exception("Latest pending frame/status was lost or concurrent sends occurred");
        using var quiet = new SlowSocket(); using var wgc = new CaptureSocketClient(quiet, () => "", _ => {});
        wgc.QueueFrame(null); await Task.Delay(30);
        if (quiet.Started.Task.IsCompleted) throw new Exception("An empty WGC startup must not occupy the frame sender");
        wgc.QueueFrame(new byte[] { 42 }); await quiet.Started.Task.WaitAsync(TimeSpan.FromSeconds(3)); quiet.Release.TrySetResult();
        using var measured = new SlowSocket();
        string metrics = "{\"type\":\"capture-metrics\",\"version\":1}";
        using var pipeline = new CaptureSocketClient(measured, () => "", _ => {}, () => metrics);
        pipeline.QueueFrame(new byte[] { 77 });
        await measured.Started.Task.WaitAsync(TimeSpan.FromSeconds(3)); measured.Release.TrySetResult();
        deadline = DateTime.UtcNow.AddSeconds(3);
        while (measured.Messages.Count < 2 && DateTime.UtcNow < deadline) await Task.Delay(5);
        var ordered = measured.Messages.ToArray();
        if (ordered.Length != 2 || ordered[0].Type != WebSocketMessageType.Binary || ordered[1].Type != WebSocketMessageType.Text || measured.MaximumConcurrent > 1)
            throw new Exception("Measurements must follow the first image and share the serialized sender");
        pipeline.QueueFrame(null); await Task.Delay(30);
        if (measured.Messages.Count != 2) throw new Exception("Unchanged metrics must not resend or spin");
        Console.WriteLine("PASS: one serialized socket send, bounded latest frame and status recovery never starve a static first frame");
    }
    private sealed class SlowSocket : WebSocket
    {
        private WebSocketState state = WebSocketState.Open;
        private int calls, concurrent;
        internal int MaximumConcurrent;
        internal TaskCompletionSource Started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource Release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal ConcurrentQueue<(WebSocketMessageType Type, byte[] Bytes)> Messages = new();
        public override WebSocketCloseStatus? CloseStatus => null;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => state;
        public override string? SubProtocol => null;
        public override void Abort() => state = WebSocketState.Aborted;
        public override void Dispose() => state = WebSocketState.Closed;
        public override Task CloseAsync(WebSocketCloseStatus closeStatus, string? description, CancellationToken token) { state = WebSocketState.Closed; return Task.CompletedTask; }
        public override Task CloseOutputAsync(WebSocketCloseStatus closeStatus, string? description, CancellationToken token) => CloseAsync(closeStatus, description, token);
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken token) => throw new NotSupportedException();
        public override async Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType messageType, bool endOfMessage, CancellationToken token)
        {
            int active = Interlocked.Increment(ref concurrent); MaximumConcurrent = Math.Max(MaximumConcurrent, active);
            try
            {
                if (Interlocked.Increment(ref calls) == 1) { Started.TrySetResult(); await Release.Task; }
                Messages.Enqueue((messageType, buffer.ToArray()));
            }
            finally { Interlocked.Decrement(ref concurrent); }
        }
    }
}
