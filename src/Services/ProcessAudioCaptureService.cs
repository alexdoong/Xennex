using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace Xennex.Services
{
    public class AudioProcessInfo
    {
        public int Pid { get; set; }
        public long Hwnd { get; set; }
        public string Name { get; set; } = string.Empty;
        public string Title { get; set; } = string.Empty;
        public bool HasActiveAudio { get; set; }
        public float PeakVolume { get; set; }
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct BLOB
    {
        public int cbSize;
        public IntPtr pBlobData;
    }

    [StructLayout(LayoutKind.Explicit)]
    internal struct PROPVARIANT
    {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(2)] public ushort wReserved1;
        [FieldOffset(4)] public ushort wReserved2;
        [FieldOffset(6)] public ushort wReserved3;
        [FieldOffset(8)] public BLOB blob;
    }

    internal enum AUDIOCLIENT_ACTIVATION_TYPE
    {
        DEFAULT = 0,
        PROCESS_LOOPBACK = 1
    }

    internal enum PROCESS_LOOPBACK_MODE
    {
        INCLUDE_TARGET_PROCESS_TREE = 0,
        EXCLUDE_TARGET_PROCESS_TREE = 1
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS
    {
        public uint TargetProcessId;
        public PROCESS_LOOPBACK_MODE ProcessLoopbackMode;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct AUDIOCLIENT_ACTIVATION_PARAMS
    {
        public AUDIOCLIENT_ACTIVATION_TYPE ActivationType;
        public AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS ProcessLoopbackParams;
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("94BE9D40-C471-4b28-A32E-047C01DC75D1")]
    internal interface IActivateAudioInterfaceCompletionHandler
    {
        void ActivateCompleted(IntPtr activateOperation);
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")]
    internal interface IAgileObject
    {
    }

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    internal delegate int GetActivateResultDelegate(IntPtr thisPtr, out int activateResult, out IntPtr activatedInterface);

    internal class AudioActivationCompletionHandler : IActivateAudioInterfaceCompletionHandler, IAgileObject
    {
        public AutoResetEvent CompletedEvent = new AutoResetEvent(false);
        public int HResult = -1;
        public IntPtr ActivatedInterface = IntPtr.Zero;

        public void ActivateCompleted(IntPtr activateOperation)
        {
            try
            {
                IntPtr vtable = Marshal.ReadIntPtr(activateOperation);
                IntPtr getResultPtr = Marshal.ReadIntPtr(vtable, 3 * IntPtr.Size);
                var getResult = Marshal.GetDelegateForFunctionPointer<GetActivateResultDelegate>(getResultPtr);
                getResult(activateOperation, out HResult, out ActivatedInterface);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[ProcessAudio] Erro ao ler resultado de ativação: {ex.Message}");
            }
            finally
            {
                CompletedEvent.Set();
            }
        }
    }

    public class ProcessAudioCaptureService : IDisposable
    {
        private static void Log(string message)
        {
            try
            {
                string line = $"[{DateTime.Now:HH:mm:ss.fff}] [ProcessAudio] {message}";
                Console.WriteLine(line);
                string logDir = System.IO.Path.Combine(AppContext.BaseDirectory, "logs");
                if (!System.IO.Directory.Exists(logDir)) System.IO.Directory.CreateDirectory(logDir);
                System.IO.File.AppendAllText(System.IO.Path.Combine(logDir, "process_audio.log"), line + Environment.NewLine);
            }
            catch {}
        }
        [DllImport("mmdevapi.dll", ExactSpelling = true)]
        private static extern int ActivateAudioInterfaceAsync(
            [In, MarshalAs(UnmanagedType.LPWStr)] string deviceInterfacePath,
            [In, MarshalAs(UnmanagedType.LPStruct)] Guid riid,
            [In] IntPtr activationParams,
            [In] IActivateAudioInterfaceCompletionHandler completionHandler,
            [Out] out IntPtr asyncOperation);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumDesktopWindows(IntPtr hDesktop, EnumWindowsProc lpfn, IntPtr lParam);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr OpenDesktop(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);

        [DllImport("user32.dll")]
        private static extern bool CloseDesktop(IntPtr hDesktop);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowTextW(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("dwmapi.dll")]
        private static extern int DwmGetWindowAttribute(IntPtr hwnd, int dwAttribute, out int pvAttribute, int cbAttribute);

        [DllImport("user32.dll")]
        private static extern IntPtr GetShellWindow();

        private class WindowEntry
        {
            public IntPtr Hwnd;
            public int Pid;
            public string ProcessName = string.Empty;
            public string Title = string.Empty;
        }

        private static List<WindowEntry> GetTopLevelWindows()
        {
            var windows = new List<WindowEntry>();
            IntPtr shell = IntPtr.Zero;
            try { shell = GetShellWindow(); } catch { }

            EnumWindowsProc callback = (hWnd, lParam) =>
            {
                if (hWnd == IntPtr.Zero || hWnd == shell) return true;
                if (!IsWindowVisible(hWnd)) return true;

                int isCloaked = 0;
                try
                {
                    DwmGetWindowAttribute(hWnd, 14 /* DWMWA_CLOAKED */, out isCloaked, sizeof(int));
                }
                catch { }
                if (isCloaked != 0) return true;

                var sb = new System.Text.StringBuilder(512);
                int len = GetWindowTextW(hWnd, sb, 512);
                string title = sb.ToString().Trim();
                if (string.IsNullOrWhiteSpace(title)) return true;

                if (title == "Program Manager" || title == "Windows Input Experience") return true;

                uint pid = 0;
                GetWindowThreadProcessId(hWnd, out pid);
                if (pid <= 4) return true;

                string pName = string.Empty;
                try
                {
                    var proc = Process.GetProcessById((int)pid);
                    pName = proc.ProcessName;
                }
                catch { }

                windows.Add(new WindowEntry
                {
                    Hwnd = hWnd,
                    Pid = (int)pid,
                    ProcessName = pName,
                    Title = title
                });

                return true;
            };

            try
            {
                EnumWindows(callback, IntPtr.Zero);
            }
            catch { }

            if (windows.Count == 0)
            {
                try
                {
                    IntPtr hDesk = OpenDesktop("default", 0, false, 0x0100 /* DESKTOP_ENUMERATE */ | 0x0001 /* DESKTOP_READOBJECTS */);
                    if (hDesk != IntPtr.Zero)
                    {
                        try
                        {
                            EnumDesktopWindows(hDesk, callback, IntPtr.Zero);
                        }
                        finally
                        {
                            CloseDesktop(hDesk);
                        }
                    }
                }
                catch { }
            }

            return windows;
        }

        private static readonly Guid MEDIASUBTYPE_IEEE_FLOAT = new Guid("00000003-0000-0010-8000-00aa00389b71");
        private static readonly Guid IID_IAudioClient = new Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2");
        private const string VAD_PROCESS_LOOPBACK = @"VAD\Process_Loopback";

        private AudioClient _audioClient;
        private Thread _captureThread;
        private CancellationTokenSource _cts;
        private readonly object _lock = new object();

        public bool IsCapturing { get; private set; }
        public int CapturedPid { get; private set; }
        public int SampleRate { get; private set; } = 48000;
        public int Channels { get; private set; } = 2;

        public event Action<byte[], int, int> OnAudioChunkAvailable;

        public List<AudioProcessInfo> GetAvailableProcesses()
        {
            var resultDict = new Dictionary<int, AudioProcessInfo>();
            int currentPid = Process.GetCurrentProcess().Id;

            // 1. Coletar todas as janelas reais visíveis no desktop
            var allWindows = GetTopLevelWindows();
            var windowByPid = new Dictionary<int, WindowEntry>();
            var windowByName = new Dictionary<string, WindowEntry>(StringComparer.OrdinalIgnoreCase);

            foreach (var win in allWindows)
            {
                if (!windowByPid.ContainsKey(win.Pid))
                {
                    windowByPid[win.Pid] = win;
                }
                if (!string.IsNullOrEmpty(win.ProcessName) && !windowByName.ContainsKey(win.ProcessName))
                {
                    windowByName[win.ProcessName] = win;
                }
            }

            // 2. Inspecionar sessões de áudio ativas do CoreAudio (WASAPI)
            try
            {
                using var enumerator = new MMDeviceEnumerator();
                using var device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
                if (device != null)
                {
                    var sessions = device.AudioSessionManager.Sessions;
                    for (int i = 0; i < sessions.Count; i++)
                    {
                        var session = sessions[i];
                        uint pid = session.GetProcessID;
                        if (pid <= 0 || pid == currentPid) continue;

                        int ipid = (int)pid;
                        string pName = "Processo " + ipid;
                        string title = string.Empty;
                        long hwnd = 0;

                        try
                        {
                            var proc = Process.GetProcessById(ipid);
                            pName = proc.ProcessName;
                            title = proc.MainWindowTitle;
                        }
                        catch { }

                        // Tenta associar janela por PID exato
                        if (windowByPid.TryGetValue(ipid, out var winInfo))
                        {
                            hwnd = winInfo.Hwnd.ToInt64();
                            if (string.IsNullOrWhiteSpace(title) || title == pName)
                            {
                                title = winInfo.Title;
                            }
                        }
                        // Se não encontrou por PID (ex: Opera/Chrome áudio renderer child), associa pelo nome do executável
                        else if (!string.IsNullOrEmpty(pName) && windowByName.TryGetValue(pName, out var nameWinInfo))
                        {
                            hwnd = nameWinInfo.Hwnd.ToInt64();
                            if (string.IsNullOrWhiteSpace(title) || title == pName)
                            {
                                title = nameWinInfo.Title;
                            }
                        }

                        float peak = 0f;
                        try
                        {
                            peak = session.AudioMeterInformation?.MasterPeakValue ?? 0f;
                        }
                        catch { }

                        resultDict[ipid] = new AudioProcessInfo
                        {
                            Pid = ipid,
                            Hwnd = hwnd,
                            Name = pName,
                            Title = string.IsNullOrWhiteSpace(title) ? pName : title,
                            HasActiveAudio = true,
                            PeakVolume = peak
                        };
                    }
                }
            }
            catch (Exception ex)
            {
                Log($"Aviso ao enumerar sessões de áudio: {ex.Message}");
            }

            // 3. Incluir processos com janelas ativas (jogos e aplicativos que podem estar silenciosos no momento)
            foreach (var win in allWindows)
            {
                if (win.Pid == currentPid) continue;

                var existing = resultDict.Values.FirstOrDefault(p => p.Hwnd == win.Hwnd.ToInt64() || p.Pid == win.Pid);
                if (existing != null)
                {
                    existing.Hwnd = win.Hwnd.ToInt64();
                    if (string.IsNullOrWhiteSpace(existing.Title) || existing.Title == existing.Name)
                    {
                        existing.Title = win.Title;
                    }
                }
                else
                {
                    resultDict[win.Pid] = new AudioProcessInfo
                    {
                        Pid = win.Pid,
                        Hwnd = win.Hwnd.ToInt64(),
                        Name = win.ProcessName,
                        Title = win.Title,
                        HasActiveAudio = false,
                        PeakVolume = 0f
                    };
                }
            }

            return resultDict.Values
                .OrderByDescending(p => p.HasActiveAudio)
                .ThenBy(p => p.Title)
                .ToList();
        }

        public bool StartCapture(int pid)
        {
            lock (_lock)
            {
                StopCapture();

                bool isSystem = (pid <= 0);
                Log(isSystem ? "Iniciando captura de áudio do sistema completo (WASAPI Loopback)..." : $"Iniciando captura de áudio exclusiva para PID {pid}...");

                _cts = new CancellationTokenSource();
                var startedEvent = new ManualResetEvent(false);
                bool success = false;

                _captureThread = new Thread(() =>
                {
                    if (isSystem)
                    {
                        RunSystemCaptureWorker(startedEvent, ref success, _cts.Token);
                    }
                    else
                    {
                        RunMtaCaptureWorker(pid, startedEvent, ref success, _cts.Token);
                    }
                })
                {
                    IsBackground = true,
                    Priority = ThreadPriority.AboveNormal,
                    Name = isSystem ? "SystemAudioCapture" : $"ProcessAudioCapture_{pid}"
                };

                _captureThread.SetApartmentState(ApartmentState.MTA);
                _captureThread.Start();

                // Aguarda inicialização do worker MTA
                startedEvent.WaitOne(4000);

                if (success)
                {
                    IsCapturing = true;
                    CapturedPid = pid;
                    Log(isSystem ? "Captura de áudio do sistema iniciada com sucesso!" : $"Captura de áudio para PID {pid} iniciada com sucesso no MTA!");
                    return true;
                }
                else
                {
                    Log(isSystem ? "Falha ao inicializar captura de áudio do sistema." : $"Falha ao inicializar captura no worker MTA para PID {pid}.");
                    StopCapture();
                    return false;
                }
            }
        }

        private void RunSystemCaptureWorker(ManualResetEvent startedEvent, ref bool success, CancellationToken token)
        {
            WasapiLoopbackCapture capture = null;
            try
            {
                capture = new WasapiLoopbackCapture();
                SampleRate = capture.WaveFormat.SampleRate;
                Channels = 2;
                int inChannels = capture.WaveFormat.Channels;
                int bitsPerSample = capture.WaveFormat.BitsPerSample;
                bool isFloat = capture.WaveFormat.Encoding == WaveFormatEncoding.IeeeFloat ||
                               (capture.WaveFormat is WaveFormatExtensible wex && wex.SubFormat == MEDIASUBTYPE_IEEE_FLOAT);

                capture.DataAvailable += (s, a) =>
                {
                    if (token.IsCancellationRequested || a.BytesRecorded == 0) return;
                    int bytesPerFrame = capture.WaveFormat.BlockAlign;
                    if (bytesPerFrame <= 0) return;
                    int numFrames = a.BytesRecorded / bytesPerFrame;
                    IntPtr unmanaged = Marshal.AllocHGlobal(a.BytesRecorded);
                    try
                    {
                        Marshal.Copy(a.Buffer, 0, unmanaged, a.BytesRecorded);
                        byte[] stereoFloatBytes = ConvertToStereoFloat32(unmanaged, numFrames, inChannels, bitsPerSample, isFloat);
                        if (stereoFloatBytes != null && stereoFloatBytes.Length > 0)
                        {
                            OnAudioChunkAvailable?.Invoke(stereoFloatBytes, SampleRate, Channels);
                        }
                    }
                    finally
                    {
                        Marshal.FreeHGlobal(unmanaged);
                    }
                };

                capture.StartRecording();
                success = true;
                startedEvent.Set();

                while (!token.IsCancellationRequested)
                {
                    Thread.Sleep(50);
                }
            }
            catch (Exception ex)
            {
                Log($"Erro na captura de áudio do sistema: {ex.Message}");
            }
            finally
            {
                startedEvent.Set();
                try { capture?.StopRecording(); } catch { }
                try { capture?.Dispose(); } catch { }
            }
        }

        private void RunMtaCaptureWorker(int pid, ManualResetEvent startedEvent, ref bool success, CancellationToken token)
        {
            IntPtr actParamsPtr = IntPtr.Zero;
            IntPtr propvarPtr = IntPtr.Zero;
            AudioClient client = null;

            try
            {
                var actParams = new AUDIOCLIENT_ACTIVATION_PARAMS
                {
                    ActivationType = AUDIOCLIENT_ACTIVATION_TYPE.PROCESS_LOOPBACK,
                    ProcessLoopbackParams = new AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS
                    {
                        TargetProcessId = (uint)pid,
                        ProcessLoopbackMode = PROCESS_LOOPBACK_MODE.INCLUDE_TARGET_PROCESS_TREE
                    }
                };

                int structSize = Marshal.SizeOf(actParams);
                actParamsPtr = Marshal.AllocHGlobal(structSize);
                Marshal.StructureToPtr(actParams, actParamsPtr, false);

                var propvar = new PROPVARIANT
                {
                    vt = 0x0041, // VT_BLOB
                    blob = new BLOB { cbSize = structSize, pBlobData = actParamsPtr }
                };

                propvarPtr = Marshal.AllocHGlobal(Marshal.SizeOf(propvar));
                Marshal.StructureToPtr(propvar, propvarPtr, false);

                var handler = new AudioActivationCompletionHandler();
                int hr = ActivateAudioInterfaceAsync(
                    VAD_PROCESS_LOOPBACK,
                    IID_IAudioClient,
                    propvarPtr,
                    handler,
                    out IntPtr asyncOp);

                if (hr != 0)
                {
                    Log($"ActivateAudioInterfaceAsync retornou HR: 0x{hr:X8}");
                    startedEvent.Set();
                    return;
                }

                if (!handler.CompletedEvent.WaitOne(3000) || handler.HResult != 0 || handler.ActivatedInterface == IntPtr.Zero)
                {
                    Log($"Falha na ativação assíncrona. HR: 0x{handler.HResult:X8}");
                    startedEvent.Set();
                    return;
                }

                // Envelopar ponteiro ativado no AudioClient do NAudio dentro do MTA
                var obj = Marshal.GetObjectForIUnknown(handler.ActivatedInterface);
                var ctor = typeof(AudioClient).GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).FirstOrDefault();
                if (ctor == null)
                {
                    Log("Não foi possível encontrar o construtor interno do AudioClient.");
                    startedEvent.Set();
                    return;
                }

                client = (AudioClient)ctor.Invoke(new object[] { obj });
                _audioClient = client;

                WaveFormat mixFormat;
                using (var enumerator = new MMDeviceEnumerator())
                using (var defaultRender = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia))
                {
                    mixFormat = defaultRender.AudioClient.MixFormat;
                }

                SampleRate = mixFormat.SampleRate;
                Channels = 2; // Padronizamos saída estéreo para streaming

                Log($"Formato de renderizacao padrao: {mixFormat.SampleRate}Hz, {mixFormat.Channels} canais, {mixFormat.BitsPerSample} bits ({mixFormat.Encoding})");

                // Inicializar no modo Shared Loopback (100ms buffer)
                client.Initialize(
                    AudioClientShareMode.Shared,
                    AudioClientStreamFlags.Loopback,
                    10000000,
                    0,
                    mixFormat,
                    Guid.Empty);

                var captureClient = client.AudioCaptureClient;
                client.Start();

                success = true;
                startedEvent.Set();

                int channels = mixFormat.Channels;
                int bitsPerSample = mixFormat.BitsPerSample;
                bool isFloat = mixFormat.Encoding == WaveFormatEncoding.IeeeFloat ||
                               (mixFormat is WaveFormatExtensible wex && wex.SubFormat == MEDIASUBTYPE_IEEE_FLOAT);

                while (!token.IsCancellationRequested)
                {
                    int packetSize = captureClient.GetNextPacketSize();
                    if (packetSize == 0)
                    {
                        Thread.Sleep(5);
                        continue;
                    }

                    while (packetSize > 0 && !token.IsCancellationRequested)
                    {
                        IntPtr bufferPtr = captureClient.GetBuffer(out int numFrames, out AudioClientBufferFlags flags);
                        if (numFrames > 0)
                        {
                            if ((flags & AudioClientBufferFlags.Silent) == 0 && bufferPtr != IntPtr.Zero)
                            {
                                byte[] stereoFloatBytes = ConvertToStereoFloat32(bufferPtr, numFrames, channels, bitsPerSample, isFloat);
                                if (stereoFloatBytes != null && stereoFloatBytes.Length > 0)
                                {
                                    OnAudioChunkAvailable?.Invoke(stereoFloatBytes, SampleRate, Channels);
                                }
                            }
                            captureClient.ReleaseBuffer(numFrames);
                        }
                        packetSize = captureClient.GetNextPacketSize();
                    }
                }
            }
            catch (Exception ex)
            {
                if (!token.IsCancellationRequested)
                {
                    Log($"Erro no loop de captura MTA: {ex.Message} | {ex.StackTrace}");
                }
            }
            finally
            {
                startedEvent.Set();
                try { client?.Stop(); } catch { }
                try { client?.Dispose(); } catch { }
                _audioClient = null;

                if (actParamsPtr != IntPtr.Zero) Marshal.FreeHGlobal(actParamsPtr);
                if (propvarPtr != IntPtr.Zero) Marshal.FreeHGlobal(propvarPtr);
            }
        }

        public void StopCapture()
        {
            lock (_lock)
            {
                if (!IsCapturing && _captureThread == null) return;

                Log($"Parando captura do PID {CapturedPid}...");
                IsCapturing = false;
                CapturedPid = 0;

                try
                {
                    _cts?.Cancel();
                }
                catch { }

                try
                {
                    _captureThread?.Join(1000);
                }
                catch { }

                _captureThread = null;
                _cts = null;
                Log("Captura parada.");
            }
        }

        private byte[] ConvertToStereoFloat32(IntPtr bufferPtr, int numFrames, int inChannels, int bitsPerSample, bool isFloat)
        {
            try
            {
                float[] stereoFloats = new float[numFrames * 2];

                if (isFloat && bitsPerSample == 32)
                {
                    if (inChannels == 2)
                    {
                        // Estéreo IEEE Float direto com ganho de áudio para clareza em jogos (1.5x)
                        float[] floats = new float[numFrames * 2];
                        Marshal.Copy(bufferPtr, floats, 0, floats.Length);
                        for (int i = 0; i < floats.Length; i++)
                        {
                            float amplified = floats[i] * 1.5f;
                            floats[i] = amplified > 1.0f ? 1.0f : (amplified < -1.0f ? -1.0f : amplified);
                        }
                        byte[] result = new byte[floats.Length * sizeof(float)];
                        Buffer.BlockCopy(floats, 0, result, 0, result.Length);
                        return result;
                    }
                    else if (inChannels == 1)
                    {
                        // Mono -> Duplicar para estéreo
                        float[] mono = new float[numFrames];
                        Marshal.Copy(bufferPtr, mono, 0, numFrames);
                        for (int i = 0; i < numFrames; i++)
                        {
                            stereoFloats[i * 2] = mono[i];
                            stereoFloats[i * 2 + 1] = mono[i];
                        }
                    }
                    else
                    {
                        // Surround (5.1 / 7.1) -> Downmix estéreo
                        float[] multi = new float[numFrames * inChannels];
                        Marshal.Copy(bufferPtr, multi, 0, multi.Length);
                        for (int i = 0; i < numFrames; i++)
                        {
                            int baseIdx = i * inChannels;
                            float left = multi[baseIdx];
                            float right = multi[baseIdx + 1];
                            float center = inChannels > 2 ? multi[baseIdx + 2] : 0f;
                            float surroundLeft = inChannels > 4 ? multi[baseIdx + 4] : 0f;
                            float surroundRight = inChannels > 5 ? multi[baseIdx + 5] : 0f;

                            stereoFloats[i * 2] = left + 0.707f * center + 0.707f * surroundLeft;
                            stereoFloats[i * 2 + 1] = right + 0.707f * center + 0.707f * surroundRight;
                        }
                    }
                }
                else if (bitsPerSample == 16)
                {
                    // 16-bit Integer PCM -> IEEE Float
                    if (inChannels == 2)
                    {
                        short[] shorts = new short[numFrames * 2];
                        Marshal.Copy(bufferPtr, shorts, 0, shorts.Length);
                        for (int i = 0; i < shorts.Length; i++)
                        {
                            stereoFloats[i] = shorts[i] / 32768.0f;
                        }
                    }
                    else
                    {
                        short[] shorts = new short[numFrames * inChannels];
                        Marshal.Copy(bufferPtr, shorts, 0, shorts.Length);
                        for (int i = 0; i < numFrames; i++)
                        {
                            int baseIdx = i * inChannels;
                            float left = shorts[baseIdx] / 32768.0f;
                            float right = inChannels > 1 ? shorts[baseIdx + 1] / 32768.0f : left;
                            stereoFloats[i * 2] = left;
                            stereoFloats[i * 2 + 1] = right;
                        }
                    }
                }
                else
                {
                    return null;
                }

                byte[] bytes = new byte[stereoFloats.Length * sizeof(float)];
                Buffer.BlockCopy(stereoFloats, 0, bytes, 0, bytes.Length);
                return bytes;
            }
            catch (Exception ex)
            {
                Log($"Erro ao converter buffer de áudio: {ex.Message}");
                return null;
            }
        }

        public void Dispose()
        {
            StopCapture();
        }
    }
}
