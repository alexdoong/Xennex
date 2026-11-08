using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using WinRT;

namespace Xennex.CaptureWorker
{
    [ComImport]
    [Guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IGraphicsCaptureItemInterop
    {
        IntPtr CreateForWindow([In] IntPtr hWnd, [In] ref Guid iid);
        IntPtr CreateForMonitor([In] IntPtr hMonitor, [In] ref Guid iid);
    }

    [ComImport]
    [Guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDirect3DDxgiInterfaceAccess
    {
        IntPtr GetInterface([In] ref Guid iid);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct POINT { public int x; public int y; }

    class Program
    {
        [DllImport("d3d11.dll", CallingConvention = CallingConvention.StdCall)]
        static extern int D3D11CreateDevice(IntPtr pAdapter, int driverType, IntPtr Software, uint Flags, IntPtr pFeatureLevels, uint FeatureLevels, uint SDKVersion, out IntPtr ppDevice, out int pFeatureLevel, out IntPtr ppImmediateContext);

        [DllImport("d3d11.dll", CallingConvention = CallingConvention.StdCall)]
        static extern int CreateDirect3D11DeviceFromDXGIDevice(IntPtr dxgiDevice, out IntPtr graphicsDevice);

        [DllImport("api-ms-win-core-winrt-string-l1-1-0.dll", CallingConvention = CallingConvention.StdCall)]
        static extern int WindowsCreateString([MarshalAs(UnmanagedType.LPWStr)] string sourceString, int length, out IntPtr hstring);

        [DllImport("api-ms-win-core-winrt-string-l1-1-0.dll", CallingConvention = CallingConvention.StdCall)]
        static extern int WindowsDeleteString(IntPtr hstring);

        [DllImport("api-ms-win-core-winrt-l1-1-0.dll", CallingConvention = CallingConvention.StdCall)]
        static extern int RoGetActivationFactory(IntPtr activatableClassId, [In] ref Guid iid, out IntPtr factory);

        [DllImport("user32.dll")]
        static extern IntPtr MonitorFromPoint(POINT pt, uint dwFlags);

        [DllImport("user32.dll")]
        static extern bool IsWindow(IntPtr hWnd);

        private static readonly ConcurrentDictionary<string, CaptureSocketClient> _clients = new();
        private static readonly object _syncLock = new();
        private static bool _isRunning = true;
        private static int _parentPid = 0;
        private static long _targetHwnd = 0;
        private static int _targetFps = 60;
        private static int _port = 59124;
        private static int _quality = 80;
        private static string _captureToken = "";
        private static int _scaleWidth = 0;
        private static int _scaleHeight = 0;
        private static byte[]? _latestFrame;
        private static string _backend = "wgc";
        private static string _display = "";
        private static int _gamePid;
        private static long _gameStartTicks;
        private static string _captureStatus = "";

        static void Log(string msg)
        {
            string line = $"[{DateTime.Now:HH:mm:ss.fff}] [CaptureWorker] {msg}";
            Console.WriteLine(line);
            try
            {
                string baseDir = AppContext.BaseDirectory;
                string logDir = Path.Combine(baseDir, "logs");
                if (!Directory.Exists(logDir)) Directory.CreateDirectory(logDir);
                File.AppendAllText(Path.Combine(logDir, "capture_worker.log"), line + Environment.NewLine);
            }
            catch { }
        }

        static async Task Main(string[] args)
        {
            Log("Iniciando Xennex.CaptureWorker (Windows.Graphics.Capture GPU Engine)...");

            // Parse Command Line
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--hwnd" && i + 1 < args.Length) long.TryParse(args[++i], out _targetHwnd);
                else if (args[i] == "--backend" && i + 1 < args.Length) _backend = args[++i];
                else if (args[i] == "--gamepid" && i + 1 < args.Length) int.TryParse(args[++i], out _gamePid);
                else if (args[i] == "--gamestart" && i + 1 < args.Length) long.TryParse(args[++i], out _gameStartTicks);
                else if (args[i] == "--display" && i + 1 < args.Length) _display = args[++i];
                else if (args[i] == "--parentpid" && i + 1 < args.Length) int.TryParse(args[++i], out _parentPid);
                else if (args[i] == "--fps" && i + 1 < args.Length) int.TryParse(args[++i], out _targetFps);
                else if (args[i] == "--port" && i + 1 < args.Length) int.TryParse(args[++i], out _port);
                else if (args[i] == "--token" && i + 1 < args.Length) _captureToken = args[++i];
                else if (args[i] == "--quality" && i + 1 < args.Length) int.TryParse(args[++i], out _quality);
                else if (args[i] == "--res" && i + 1 < args.Length)
                {
                    string res = args[++i].ToLowerInvariant();
                    if (res == "1080p") { _scaleWidth = 1920; _scaleHeight = 1080; }
                    else if (res == "720p") { _scaleWidth = 1280; _scaleHeight = 720; }
                    else if (res == "1440p" || res == "2k") { _scaleWidth = 2560; _scaleHeight = 1440; }
                    else if (res == "source") { _scaleWidth = 0; _scaleHeight = 0; }
                    else if (res == "480p") { _scaleWidth = 854; _scaleHeight = 480; }
                    else if (res == "4k" || res == "2160p") { _scaleWidth = 3840; _scaleHeight = 2160; }
                }
            }

            if (_captureToken.Length != 64) { Log("Token de captura ausente; inicialização recusada."); return; }
            if (_backend is not ("wgc" or "dxgi" or "game") || (_backend == "dxgi" && (_targetHwnd != 0 || string.IsNullOrWhiteSpace(_display))) ||
                (_backend == "game" && (_targetHwnd == 0 || _gamePid <= 0 || _gameStartTicks <= 0)))
            { Log("Configuração de captura inválida; nenhum monitor alternativo será capturado."); return; }
            if (_targetFps <= 0) _targetFps = 120;
            if (_targetFps > 120) _targetFps = 120;
            var cadence = new Xennex.Services.CaptureFrameCadence(_targetFps);
            var idleCadence = new Xennex.Services.CaptureFrameCadence(4);

            Log($"Configuração: HWND=0x{_targetHwnd:X}, FPS={_targetFps}, Port={_port}, Quality={_quality}, ParentPID={_parentPid}");

            // Start Parent Watchdog Thread
            if (_parentPid > 0)
            {
                _ = Task.Run(async () =>
                {
                    while (_isRunning)
                    {
                        try
                        {
                            using var parent = Process.GetProcessById(_parentPid);
                            if (parent.HasExited)
                            {
                                Log("Processo pai finalizado. Encerrando CaptureWorker imediatamente.");
                                _isRunning = false;
                                Environment.Exit(0);
                            }
                        }
                        catch
                        {
                            Log("Falha ao monitorar processo pai. Encerrando CaptureWorker.");
                            _isRunning = false;
                            Environment.Exit(0);
                        }
                        await Task.Delay(1000);
                    }
                });
            }

            // Start WebSocket HTTP Server
            var httpListener = new HttpListener();
            httpListener.Prefixes.Add($"http://127.0.0.1:{_port}/videostream/");
            try
            {
                httpListener.Start();
                Log($"Servidor de streaming de vídeo ouvindo em ws://127.0.0.1:{_port}/videostream/");
                _ = Task.Run(() => AcceptWebSocketsAsync(httpListener));
            }
            catch (Exception ex)
            {
                Log($"Falha ao iniciar HttpListener na porta {_port}: {ex.Message}");
                return;
            }

            if (_backend == "game")
            {
                try { await GameCapture.RunAsync(_gamePid, _targetHwnd, _gameStartTicks, _targetFps, _scaleWidth, _scaleHeight, _quality,
                    () => _isRunning, BroadcastFrame, SetCaptureStatus, MeasureFrame); }
                catch (Exception ex) { Log($"Captura de jogo encerrada: {ex.Message}"); Environment.ExitCode = 1; }
                finally { _isRunning = false; httpListener.Close(); }
                return;
            }
            if (_backend == "dxgi")
            {
                try
                {
                    await DesktopDuplicationCapture.RunAsync(_display, _targetFps, _scaleWidth, _scaleHeight, _quality,
                        () => _isRunning, () => !_clients.IsEmpty, BroadcastFrame, SetCaptureStatus, Log, measure: MeasureFrame);
                }
                catch (Exception ex) { Log($"Captura DXGI encerrada: {ex.Message}"); Environment.ExitCode = 1; }
                finally { _isRunning = false; httpListener.Close(); }
                return;
            }

            // 1. Initialize Direct3D11 Device
            const uint D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20;
            int hrD3D = D3D11CreateDevice(IntPtr.Zero, 1, IntPtr.Zero, D3D11_CREATE_DEVICE_BGRA_SUPPORT, IntPtr.Zero, 0, 7, out IntPtr pD3DDevice, out _, out IntPtr pContext);
            if (hrD3D != 0)
            {
                Log($"Erro crítico ao criar ID3D11Device: 0x{hrD3D:X8}");
                return;
            }

            Guid dxgiDeviceGuid = new Guid("54ec77fa-1377-44e6-8c32-88fd5f44c84c");
            Marshal.QueryInterface(pD3DDevice, ref dxgiDeviceGuid, out IntPtr pDxgiDevice);
            CreateDirect3D11DeviceFromDXGIDevice(pDxgiDevice, out IntPtr pInspectable);
            IDirect3DDevice winrtDevice = WinRT.MarshalInspectable<IDirect3DDevice>.FromAbi(pInspectable);

            // 2. Initialize WGC Interop Factory
            string className = "Windows.Graphics.Capture.GraphicsCaptureItem";
            WindowsCreateString(className, className.Length, out IntPtr hstring);
            Guid interopGuid = new Guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356");
            RoGetActivationFactory(hstring, ref interopGuid, out IntPtr factoryPtr);
            WindowsDeleteString(hstring);
            var interop = (IGraphicsCaptureItemInterop)Marshal.GetObjectForIUnknown(factoryPtr);

            // 3. Capture only the requested surface; a closed window must never expose the desktop.
            GraphicsCaptureItem? item = null;
            Guid itemGuid = new Guid("79C3F95B-31F7-4EC2-A464-632EF5D30760");

            if (_targetHwnd != 0 && IsWindow((IntPtr)_targetHwnd))
            {
                IntPtr itemPtr = interop.CreateForWindow((IntPtr)_targetHwnd, ref itemGuid);
                if (itemPtr != IntPtr.Zero)
                {
                    item = WinRT.MarshalInspectable<GraphicsCaptureItem>.FromAbi(itemPtr);
                    Log($"Capturando Janela Selecionada: '{item.DisplayName}' ({item.Size.Width}x{item.Size.Height})");
                }
            }

            if (item == null)
            {
                if (_targetHwnd != 0)
                {
                    Log("A janela selecionada não está disponível. Captura encerrada sem trocar para o monitor.");
                    return;
                }
                IntPtr hMon = MonitorFromPoint(new POINT { x = 0, y = 0 }, 1);
                IntPtr itemPtr = interop.CreateForMonitor(hMon, ref itemGuid);
                item = WinRT.MarshalInspectable<GraphicsCaptureItem>.FromAbi(itemPtr);
                Log($"Capturando Monitor Primário: '{item.DisplayName}' ({item.Size.Width}x{item.Size.Height})");
            }

            // Wrappers own one additional COM reference; the WinRT device still borrows the originals.
            Marshal.AddRef(pD3DDevice); Marshal.AddRef(pContext);
            using var captureDevice = new Vortice.Direct3D11.ID3D11Device(pD3DDevice);
            using var captureContext = new Vortice.Direct3D11.ID3D11DeviceContext(pContext);
            using var frameEncoder = new GpuFrameEncoder(captureDevice, captureContext, _quality, Log);
            var poolSize = item.Size;

            // 4. Create Capture FramePool and Session
            var framePool = Direct3D11CaptureFramePool.CreateFreeThreaded(winrtDevice, DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, item.Size);
            var session = framePool.CreateCaptureSession(item);
            try { session.IsCursorCaptureEnabled = true; } catch { }

            int frameCount = 0;
            var swFps = Stopwatch.StartNew();

            framePool.FrameArrived += (s, a) =>
            {
                lock (_syncLock)
                {
                    if (!_isRunning) return;
                    try
                    {
                        using var frame = s.TryGetNextFrame();
                        if (frame == null) return;
                        var size = frame.ContentSize;
                        if (size.Width <= 0 || size.Height <= 0) return;
                        if (size.Width != poolSize.Width || size.Height != poolSize.Height)
                        {
                            // The old pool surface has the old dimensions: discard it before recreation.
                            frame.Dispose();
                            s.Recreate(winrtDevice, DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, size);
                            poolSize = size;
                            return;
                        }
                        double nowMs = Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency;
                        // Keep a fresh startup image without encoding at full rate after a client disappears.
                        if (_clients.IsEmpty && !idleCadence.ShouldCapture(nowMs)) return;
                        if (!cadence.ShouldCapture(nowMs)) return;
                        var access = frame.Surface.As<IDirect3DDxgiInterfaceAccess>();
                        Guid texGuid = new Guid("6f15aaf2-d208-4e89-9ab4-489535d34f9c");
                        IntPtr texture = access.GetInterface(ref texGuid);
                        if (texture == IntPtr.Zero) return;
                        try
                        {
                            // GetInterface returned an owned reference, released by this wrapper.
                            using var captured = new Vortice.Direct3D11.ID3D11Texture2D(texture);
                            texture = IntPtr.Zero;
                            byte[] jpeg = frameEncoder.Encode(captured, _scaleWidth, _scaleHeight);
                            MeasureFrame(frameEncoder.LastSample);
                            BroadcastFrame(jpeg);
                            frameCount++;
                            if (swFps.ElapsedMilliseconds >= 5000)
                            {
                                Log($"Captura real: {frameCount / swFps.Elapsed.TotalSeconds:F1} FPS | {jpeg.Length / 1024} KB/frame | Clientes: {_clients.Count}");
                                frameCount = 0;
                                swFps.Restart();
                            }
                        }
                        finally { if (texture != IntPtr.Zero) Marshal.Release(texture); }
                    }
                    catch (Exception ex) { Log($"Falha no frame: {ex.Message}"); }
                }
            };

            Log("Iniciando captura contínua na GPU...");
            session.StartCapture();

            // Wait for shutdown trigger
            Console.CancelKeyPress += (s, e) =>
            {
                e.Cancel = true;
                _isRunning = false;
            };

            while (_isRunning)
            {
                await Task.Delay(500);
            }

            Log("Encerrando captura e liberando recursos da GPU...");
            session.Dispose();
            framePool.Dispose();
            lock (_syncLock) { /* Wait for an in-flight frame before disposing the using resources. */ }
            Marshal.Release(pContext);
            Marshal.Release(pD3DDevice);
            Log("Recursos liberados com sucesso. Zero vazamentos.");
        }

        private static readonly CaptureTelemetry Telemetry = new();
        private static string _captureMetrics = "";
        private static void MeasureFrame(FrameStageSample sample)
        {
            if (!Telemetry.Add(sample, Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency)) return;
            Volatile.Write(ref _captureMetrics, Telemetry.Snapshot);
            Log($"Pipeline {sample.ScalePath}: {sample.SourceWidth}x{sample.SourceHeight} → {sample.OutputWidth}x{sample.OutputHeight}; readback {sample.MappedBytes / 1048576.0:F1} MiB/frame");
        }

        private static void BroadcastFrame(byte[] jpegBytes)
        {
            // A static source may only produce a frame before the browser connects.
            Volatile.Write(ref _latestFrame, jpegBytes);
            foreach (var kvp in _clients)
            {
                var client = kvp.Value;
                var socket = client.Socket;
                if (socket != null && socket.State == WebSocketState.Open)
                {
                    SendFrame(client, jpegBytes);
                }
                else
                {
                    _clients.TryRemove(kvp.Key, out _);
                }
            }
        }

        private static void SetCaptureStatus(string status)
        {
            Interlocked.Exchange(ref _captureStatus, status);
            // Ready must travel with the first JPEG, or the send guard could discard that only static frame.
            if (status is not ("recovering" or "unstable")) return;
            foreach (var client in _clients.Values) SendFrame(client, null);
        }

        private static void SendFrame(CaptureSocketClient client, byte[]? frame) => client.QueueFrame(frame);

        private static async Task AcceptWebSocketsAsync(HttpListener listener)
        {
            while (listener.IsListening && _isRunning)
            {
                try
                {
                    var context = await listener.GetContextAsync();
                    if (!Xennex.Services.Security.LocalRequestPolicy.IsCaptureAllowed(context.Request.Headers["Origin"], context.Request.QueryString["token"], _captureToken))
                    {
                        context.Response.StatusCode = 403; context.Response.Close(); continue;
                    }
                    if (context.Request.IsWebSocketRequest)
                    {
                        var wsContext = await context.AcceptWebSocketAsync(null);
                        string clientId = Guid.NewGuid().ToString();
                        var session = new CaptureSocketClient(wsContext.WebSocket, () => Volatile.Read(ref _captureStatus), Log, () => Volatile.Read(ref _captureMetrics));
                        _clients[clientId] = session;
                        var cached = Volatile.Read(ref _latestFrame);
                        SendFrame(session, cached);
                        Log($"Cliente conectado ao stream de vídeo ({clientId})");

                        _ = Task.Run(async () =>
                        {
                            var buf = new byte[1024];
                            try
                            {
                                while (wsContext.WebSocket.State == WebSocketState.Open)
                                {
                                    var result = await wsContext.WebSocket.ReceiveAsync(new ArraySegment<byte>(buf), CancellationToken.None);
                                    if (result.MessageType == WebSocketMessageType.Close) break;
                                }
                            }
                            catch { }
                            finally
                            {
                                _clients.TryRemove(clientId, out _);
                                session.Dispose();
                                Log($"Cliente desconectado ({clientId})");
                            }
                        });
                    }
                    else
                    {
                        context.Response.StatusCode = 400;
                        context.Response.Close();
                    }
                }
                catch
                {
                    if (!_isRunning) break;
                }
            }
        }

    }
}
