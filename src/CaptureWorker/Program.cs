using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
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

    [StructLayout(LayoutKind.Sequential)]
    struct D3D11_TEXTURE2D_DESC
    {
        public uint Width;
        public uint Height;
        public uint MipLevels;
        public uint ArraySize;
        public uint Format;
        public uint SampleDescCount;
        public uint SampleDescQuality;
        public uint Usage;
        public uint BindFlags;
        public uint CPUAccessFlags;
        public uint MiscFlags;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct D3D11_MAPPED_SUBRESOURCE
    {
        public IntPtr pData;
        public uint RowPitch;
        public uint DepthPitch;
    }

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

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        delegate int CreateTexture2DDelegate(IntPtr thisPtr, ref D3D11_TEXTURE2D_DESC desc, IntPtr initialData, out IntPtr ppTexture2D);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        delegate void CopyResourceDelegate(IntPtr thisPtr, IntPtr pDstResource, IntPtr pSrcResource);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        delegate int MapDelegate(IntPtr thisPtr, IntPtr pResource, uint Subresource, uint MapType, uint MapFlags, out D3D11_MAPPED_SUBRESOURCE pMappedResource);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        delegate void UnmapDelegate(IntPtr thisPtr, IntPtr pResource, uint Subresource);

        private class ClientSession
        {
            public WebSocket Socket;
            public int IsSending;
        }

        private static readonly ConcurrentDictionary<string, ClientSession> _clients = new();
        private static readonly object _syncLock = new();
        private static bool _isRunning = true;
        private static int _parentPid = 0;
        private static long _targetHwnd = 0;
        private static int _targetFps = 60;
        private static int _port = 59124;
        private static int _quality = 80;
        private static int _scaleWidth = 0;
        private static int _scaleHeight = 0;
        private static long _lastFrameTicks = 0;

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
                else if (args[i] == "--parentpid" && i + 1 < args.Length) int.TryParse(args[++i], out _parentPid);
                else if (args[i] == "--fps" && i + 1 < args.Length) int.TryParse(args[++i], out _targetFps);
                else if (args[i] == "--port" && i + 1 < args.Length) int.TryParse(args[++i], out _port);
                else if (args[i] == "--quality" && i + 1 < args.Length) int.TryParse(args[++i], out _quality);
                else if (args[i] == "--res" && i + 1 < args.Length)
                {
                    string res = args[++i];
                    if (res == "1080p") { _scaleWidth = 1920; _scaleHeight = 1080; }
                    else if (res == "720p") { _scaleWidth = 1280; _scaleHeight = 720; }
                    else if (res == "1440p") { _scaleWidth = 2560; _scaleHeight = 1440; }
                }
            }

            if (_targetFps < 15) _targetFps = 30;
            if (_targetFps > 120) _targetFps = 120;
            long minTicksPerFrame = Stopwatch.Frequency / _targetFps;

            Log($"Configuração: HWND=0x{_targetHwnd:X}, FPS={_targetFps}, Port={_port}, Quality={_quality}, ParentPID={_parentPid}");

            // Start Parent Watchdog Thread
            if (_parentPid > 0)
            {
                Task.Run(async () =>
                {
                    while (_isRunning)
                    {
                        try
                        {
                            var parent = Process.GetProcessById(_parentPid);
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

            // 3. Create GraphicsCaptureItem for Target Window (or Monitor fallback)
            GraphicsCaptureItem item = null;
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
                Log("Aviso: Janela específica não pôde ser criada. Usando Monitor Primário como fallback.");
                IntPtr hMon = MonitorFromPoint(new POINT { x = 0, y = 0 }, 1);
                IntPtr itemPtr = interop.CreateForMonitor(hMon, ref itemGuid);
                item = WinRT.MarshalInspectable<GraphicsCaptureItem>.FromAbi(itemPtr);
                Log($"Capturando Monitor Primário: '{item.DisplayName}' ({item.Size.Width}x{item.Size.Height})");
            }

            // Direct3D 11 Delegates
            IntPtr d3dDevVtable = Marshal.ReadIntPtr(pD3DDevice);
            var createTexture2D = Marshal.GetDelegateForFunctionPointer<CreateTexture2DDelegate>(Marshal.ReadIntPtr(d3dDevVtable, 5 * IntPtr.Size));

            IntPtr ctxVtable = Marshal.ReadIntPtr(pContext);
            var copyResource = Marshal.GetDelegateForFunctionPointer<CopyResourceDelegate>(Marshal.ReadIntPtr(ctxVtable, 47 * IntPtr.Size));
            var map = Marshal.GetDelegateForFunctionPointer<MapDelegate>(Marshal.ReadIntPtr(ctxVtable, 14 * IntPtr.Size));
            var unmap = Marshal.GetDelegateForFunctionPointer<UnmapDelegate>(Marshal.ReadIntPtr(ctxVtable, 15 * IntPtr.Size));

            // Create Staging Texture
            var desc = new D3D11_TEXTURE2D_DESC
            {
                Width = (uint)item.Size.Width,
                Height = (uint)item.Size.Height,
                MipLevels = 1,
                ArraySize = 1,
                Format = 87, // DXGI_FORMAT_B8G8R8A8_UNORM
                SampleDescCount = 1,
                SampleDescQuality = 0,
                Usage = 3, // D3D11_USAGE_STAGING
                BindFlags = 0,
                CPUAccessFlags = 0x20000, // D3D11_CPU_ACCESS_READ
                MiscFlags = 0
            };

            int hrTex = createTexture2D(pD3DDevice, ref desc, IntPtr.Zero, out IntPtr pStagingTexture);
            if (hrTex != 0)
            {
                Log($"Falha ao criar staging texture: 0x{hrTex:X8}");
                return;
            }

            // 4. Create Capture FramePool and Session
            var framePool = Direct3D11CaptureFramePool.CreateFreeThreaded(winrtDevice, DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, item.Size);
            var session = framePool.CreateCaptureSession(item);
            try { session.IsCursorCaptureEnabled = true; } catch { }

            var encoder = GetEncoder(ImageFormat.Jpeg);
            var encParams = new EncoderParameters(1);
            encParams.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, (long)_quality);

            int frameCount = 0;
            var swFps = Stopwatch.StartNew();

            framePool.FrameArrived += (s, a) =>
            {
                if (!_isRunning) return;

                // Rate limiting to target FPS
                long currentTicks = Stopwatch.GetTimestamp();
                if (currentTicks - _lastFrameTicks < minTicksPerFrame)
                {
                    // Discard frame to match target FPS
                    using var discarded = s.TryGetNextFrame();
                    return;
                }
                _lastFrameTicks = currentTicks;

                try
                {
                    using var frame = s.TryGetNextFrame();
                    if (frame == null) return;

                    // Only process frame if there are connected clients
                    if (_clients.IsEmpty) return;

                    var access = frame.Surface.As<IDirect3DDxgiInterfaceAccess>();
                    Guid texGuid = new Guid("6f15aaf2-d208-4e89-9ab4-489535d34f9c");
                    IntPtr pGpuTexture = access.GetInterface(ref texGuid);

                    if (pGpuTexture != IntPtr.Zero)
                    {
                        copyResource(pContext, pStagingTexture, pGpuTexture);

                        int hrMap = map(pContext, pStagingTexture, 0, 1 /* D3D11_MAP_READ */, 0, out D3D11_MAPPED_SUBRESOURCE mapped);
                        if (hrMap == 0 && mapped.pData != IntPtr.Zero)
                        {
                            int width = item.Size.Width;
                            int height = item.Size.Height;
                            int pitch = (int)mapped.RowPitch;

                            byte[] jpegBytes = null;

                            using (var bmp = new Bitmap(width, height, pitch, PixelFormat.Format32bppArgb, mapped.pData))
                            {
                                // Optional downscaling
                                if (_scaleWidth > 0 && _scaleHeight > 0 && (_scaleWidth < width || _scaleHeight < height))
                                {
                                    using (var scaledBmp = new Bitmap(bmp, new Size(_scaleWidth, _scaleHeight)))
                                    {
                                        using (var ms = new MemoryStream())
                                        {
                                            scaledBmp.Save(ms, encoder, encParams);
                                            jpegBytes = ms.ToArray();
                                        }
                                    }
                                }
                                else
                                {
                                    using (var ms = new MemoryStream())
                                    {
                                        bmp.Save(ms, encoder, encParams);
                                        jpegBytes = ms.ToArray();
                                    }
                                }
                            }

                            unmap(pContext, pStagingTexture, 0);

                            if (jpegBytes != null && jpegBytes.Length > 0)
                            {
                                BroadcastFrame(jpegBytes);
                                frameCount++;
                                if (swFps.ElapsedMilliseconds >= 5000)
                                {
                                    double fps = frameCount / (swFps.ElapsedMilliseconds / 1000.0);
                                    Log($"Status da Transmissão: {fps:F1} FPS ativos | Tamanho: {jpegBytes.Length / 1024} KB | Clientes: {_clients.Count}");
                                    frameCount = 0;
                                    swFps.Restart();
                                }
                            }
                        }

                        Marshal.Release(pGpuTexture);
                    }
                }
                catch (Exception ex)
                {
                    Log($"Aviso de processamento de frame: {ex.Message}");
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
            Marshal.Release(pStagingTexture);
            Marshal.Release(pContext);
            Marshal.Release(pD3DDevice);
            Log("Recursos liberados com sucesso. Zero vazamentos.");
        }

        private static void BroadcastFrame(byte[] jpegBytes)
        {
            var buffer = new ArraySegment<byte>(jpegBytes);
            foreach (var kvp in _clients)
            {
                var client = kvp.Value;
                if (client.Socket.State == WebSocketState.Open)
                {
                    if (Interlocked.CompareExchange(ref client.IsSending, 1, 0) == 0)
                    {
                        _ = Task.Run(async () =>
                        {
                            try
                            {
                                if (client.Socket.State == WebSocketState.Open)
                                {
                                    await client.Socket.SendAsync(buffer, WebSocketMessageType.Binary, true, CancellationToken.None);
                                }
                            }
                            catch (Exception ex)
                            {
                                Log($"Erro ao transmitir frame: {ex.Message}");
                            }
                            finally
                            {
                                Interlocked.Exchange(ref client.IsSending, 0);
                            }
                        });
                    }
                }
                else
                {
                    _clients.TryRemove(kvp.Key, out _);
                }
            }
        }

        private static async Task AcceptWebSocketsAsync(HttpListener listener)
        {
            while (listener.IsListening && _isRunning)
            {
                try
                {
                    var context = await listener.GetContextAsync();
                    if (context.Request.IsWebSocketRequest)
                    {
                        var wsContext = await context.AcceptWebSocketAsync(null);
                        string clientId = Guid.NewGuid().ToString();
                        var session = new ClientSession { Socket = wsContext.WebSocket, IsSending = 0 };
                        _clients[clientId] = session;
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

        private static ImageCodecInfo GetEncoder(ImageFormat format)
        {
            var codecs = ImageCodecInfo.GetImageEncoders();
            foreach (var codec in codecs)
            {
                if (codec.FormatID == format.Guid) return codec;
            }
            return null;
        }
    }
}
