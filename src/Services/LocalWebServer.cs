using Xennex.Services.Security;
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;

namespace Xennex.Services
{
    public class LocalWebServer
    {
        private HttpListener _listener;
        private readonly string _wwwrootDir;
        public const int Port = 59123;
        private readonly int _port;
        private bool _isRunning = false;

        private readonly ConcurrentDictionary<Guid, Channel<byte[]>> _activeClients = new ConcurrentDictionary<Guid, Channel<byte[]>>();

        public Func<(int SampleRate, int Channels)> AudioFormatProvider { get; set; }

        public int CurrentSampleRate { get; set; } = 48000;
        public int CurrentChannels { get; set; } = 2;

        public LocalWebServer(string wwwrootDir, int port = Port)
        {
            _wwwrootDir = wwwrootDir;
            _port = port;
        }

        public void Start()
        {
            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add($"http://localhost:{_port}/");
                _listener.Prefixes.Add($"http://127.0.0.1:{_port}/");
                _listener.Start();
                _isRunning = true;
                Task.Run(ListenLoop);
                Console.WriteLine($"[LocalWebServer] Serving from {_wwwrootDir} at http://localhost:{_port}/");
            }
            catch (Exception ex)
            {
                AppLog.Error("LocalWebServer.Start", ex);
            }
        }

        private async Task ListenLoop()
        {
            while (_isRunning && _listener != null && _listener.IsListening)
            {
                try
                {
                    var context = await _listener.GetContextAsync();
                    if (context.Request.IsWebSocketRequest && !LocalRequestPolicy.IsCaptureAllowed(context.Request.Headers["Origin"], context.Request.QueryString["token"], LocalRequestPolicy.CaptureToken))
                    {
                        context.Response.StatusCode = 403; context.Response.Close(); continue;
                    }
                    if (context.Request.IsWebSocketRequest && context.Request.Url.AbsolutePath.TrimEnd('/').Equals("/audiostream", StringComparison.OrdinalIgnoreCase))
                    {
                        _ = HandleAudioWebSocketAsync(context);
                    }
                    else
                    {
                        ProcessRequest(context);
                    }
                }
                catch (Exception error)
                {
                    if (!_isRunning) break;
                    AppLog.Error("LocalWebServer.Listen", error);
                }
            }
        }

        private async Task HandleAudioWebSocketAsync(HttpListenerContext context)
        {
            HttpListenerWebSocketContext wsContext = null;
            try
            {
                wsContext = await context.AcceptWebSocketAsync(subProtocol: null);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[LocalWebServer] Erro ao aceitar WebSocket: {ex.Message}");
                return;
            }

            var webSocket = wsContext.WebSocket;
            var clientId = Guid.NewGuid();

            var channel = Channel.CreateBounded<byte[]>(new BoundedChannelOptions(20)
            {
                FullMode = BoundedChannelFullMode.DropOldest,
                SingleReader = true,
                SingleWriter = false
            });

            _activeClients[clientId] = channel;
            Console.WriteLine($"[LocalWebServer] Cliente WebSocket de áudio conectado ({clientId})");

            // Enviar handshake inicial com informações de formato
            try
            {
                var format = AudioFormatProvider?.Invoke() ?? (CurrentSampleRate, CurrentChannels);
                CurrentSampleRate = format.Item1;
                CurrentChannels = format.Item2;
                string formatJson = $"{{\"type\":\"format\",\"sampleRate\":{CurrentSampleRate},\"channels\":{CurrentChannels}}}";
                byte[] formatBytes = Encoding.UTF8.GetBytes(formatJson);
                await webSocket.SendAsync(new ArraySegment<byte>(formatBytes), WebSocketMessageType.Text, true, CancellationToken.None);
            }
            catch { }

            using var cts = new CancellationTokenSource();

            // Loop de envio de chunks de áudio em background
            var senderTask = Task.Run(async () =>
            {
                try
                {
                    while (!cts.Token.IsCancellationRequested && webSocket.State == WebSocketState.Open)
                    {
                        if (await channel.Reader.WaitToReadAsync(cts.Token))
                        {
                            while (channel.Reader.TryRead(out byte[] chunk))
                            {
                                if (webSocket.State != WebSocketState.Open) break;
                                await webSocket.SendAsync(new ArraySegment<byte>(chunk), WebSocketMessageType.Binary, true, cts.Token);
                            }
                        }
                    }
                }
                catch { }
            });

            // Loop de recepção para detectar fechamento
            byte[] recvBuf = new byte[512];
            try
            {
                while (webSocket.State == WebSocketState.Open && !cts.Token.IsCancellationRequested)
                {
                    var result = await webSocket.ReceiveAsync(new ArraySegment<byte>(recvBuf), cts.Token);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", CancellationToken.None);
                        break;
                    }
                }
            }
            catch { }
            finally
            {
                cts.Cancel();
                _activeClients.TryRemove(clientId, out _);
                try { await senderTask; } catch { }
                try { webSocket.Dispose(); } catch { }
                Console.WriteLine($"[LocalWebServer] Cliente WebSocket de áudio desconectado ({clientId})");
            }
        }

        public void BroadcastAudioChunk(byte[] data, int sampleRate = 48000, int channels = 2)
        {
            CurrentSampleRate = sampleRate;
            CurrentChannels = channels;

            if (_activeClients.IsEmpty) return;

            foreach (var kvp in _activeClients)
            {
                kvp.Value.Writer.TryWrite(data);
            }
        }

        private void ProcessRequest(HttpListenerContext context)
        {
            try
            {
                if (context.Request.HttpMethod != "GET" && context.Request.HttpMethod != "HEAD")
                { context.Response.StatusCode = 405; return; }
                // No cross-origin fetches; WS authorization is separate from CORS.
                string origin = context.Request.Headers["Origin"];
                if (origin != null && origin != $"http://localhost:{_port}" && origin != $"http://127.0.0.1:{_port}")
                { context.Response.StatusCode = 403; return; }
                string filePath = LocalRequestPolicy.ResolvePublicFile(_wwwrootDir, context.Request.RawUrl);
                if (filePath == null) { context.Response.StatusCode = 403; return; }
                if (File.Exists(filePath))
                {
                    byte[] bytes = File.ReadAllBytes(filePath);
                    string ext = Path.GetExtension(filePath).ToLower();
                    context.Response.ContentType = ext switch
                    {
                        ".html" => "text/html; charset=utf-8",
                        ".js" => "application/javascript; charset=utf-8",
                        ".css" => "text/css; charset=utf-8",
                        ".json" => "application/json",
                        ".png" => "image/png",
                        ".svg" => "image/svg+xml",
                        _ => "application/octet-stream"
                    };
                    context.Response.Headers.Add("X-Content-Type-Options", "nosniff");
                    context.Response.Headers.Add("Cross-Origin-Resource-Policy", "same-origin");
                    context.Response.StatusCode = 200;
                    context.Response.ContentLength64 = bytes.Length;
                    if (context.Request.HttpMethod == "GET") context.Response.OutputStream.Write(bytes, 0, bytes.Length);
                }
                else
                {
                    context.Response.StatusCode = 404;
                }
            }
            catch (Exception error) { AppLog.Error("LocalWebServer.Request", error); }
            finally { try { context.Response.Close(); } catch (Exception error) { AppLog.Error("LocalWebServer.Close", error); } }
        }

        public void Stop()
        {
            _isRunning = false;
            try { _listener?.Stop(); _listener?.Close(); } catch { }
        }
    }
}
