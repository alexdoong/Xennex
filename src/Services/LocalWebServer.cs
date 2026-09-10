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
        private bool _isRunning = false;

        private readonly ConcurrentDictionary<Guid, Channel<byte[]>> _activeClients = new ConcurrentDictionary<Guid, Channel<byte[]>>();

        public int CurrentSampleRate { get; set; } = 48000;
        public int CurrentChannels { get; set; } = 2;

        public LocalWebServer(string wwwrootDir)
        {
            _wwwrootDir = wwwrootDir;
        }

        public void Start()
        {
            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add($"http://localhost:{Port}/");
                _listener.Prefixes.Add($"http://127.0.0.1:{Port}/");
                _listener.Start();
                _isRunning = true;
                Task.Run(ListenLoop);
                Console.WriteLine($"[LocalWebServer] Serving from {_wwwrootDir} at http://localhost:{Port}/");
            }
            catch (Exception ex)
            {
                Console.WriteLine("[LocalWebServer] Could not bind to port: " + ex.Message);
            }
        }

        private async Task ListenLoop()
        {
            while (_isRunning && _listener != null && _listener.IsListening)
            {
                try
                {
                    var context = await _listener.GetContextAsync();
                    if (context.Request.IsWebSocketRequest && context.Request.Url.AbsolutePath.TrimEnd('/').Equals("/audiostream", StringComparison.OrdinalIgnoreCase))
                    {
                        _ = HandleAudioWebSocketAsync(context);
                    }
                    else
                    {
                        ProcessRequest(context);
                    }
                }
                catch
                {
                    if (!_isRunning) break;
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
                string rawUrl = context.Request.Url.AbsolutePath.TrimStart('/');
                if (string.IsNullOrEmpty(rawUrl) || rawUrl == "/") rawUrl = "watch.html";

                string filePath = Path.Combine(_wwwrootDir, rawUrl.Replace('/', Path.DirectorySeparatorChar));
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
                    context.Response.Headers.Add("Access-Control-Allow-Origin", "*");
                    context.Response.StatusCode = 200;
                    context.Response.OutputStream.Write(bytes, 0, bytes.Length);
                }
                else
                {
                    context.Response.StatusCode = 404;
                }
                context.Response.Close();
            }
            catch { }
        }

        public void Stop()
        {
            _isRunning = false;
            try { _listener?.Stop(); _listener?.Close(); } catch { }
        }
    }
}
