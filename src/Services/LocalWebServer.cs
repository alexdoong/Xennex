using System;
using System.IO;
using System.Net;
using System.Threading.Tasks;

namespace Xennex.Services
{
    public class LocalWebServer
    {
        private HttpListener _listener;
        private readonly string _wwwrootDir;
        public const int Port = 59123;
        private bool _isRunning = false;

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
                    ProcessRequest(context);
                }
                catch
                {
                    if (!_isRunning) break;
                }
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
