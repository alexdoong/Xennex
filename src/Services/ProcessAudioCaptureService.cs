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

            // 1. Inspecionar sessões de áudio ativas do CoreAudio (WASAPI)
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
                        try
                        {
                            var proc = Process.GetProcessById(ipid);
                            pName = proc.ProcessName;
                            title = proc.MainWindowTitle;
                        }
                        catch { }

                        float peak = 0f;
                        try
                        {
                            peak = session.AudioMeterInformation?.MasterPeakValue ?? 0f;
                        }
                        catch { }

                        resultDict[ipid] = new AudioProcessInfo
                        {
                            Pid = ipid,
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

            // 2. Incluir processos com janelas ativas (jogos e aplicativos que podem estar silenciosos no momento)
            try
            {
                var processes = Process.GetProcesses();
                foreach (var proc in processes)
                {
                    try
                    {
                        if (proc.Id == currentPid || proc.Id <= 4) continue;
                        if (proc.MainWindowHandle != IntPtr.Zero && !string.IsNullOrWhiteSpace(proc.MainWindowTitle))
                        {
                            if (!resultDict.ContainsKey(proc.Id))
                            {
                                resultDict[proc.Id] = new AudioProcessInfo
                                {
                                    Pid = proc.Id,
                                    Name = proc.ProcessName,
                                    Title = proc.MainWindowTitle,
                                    HasActiveAudio = false,
                                    PeakVolume = 0f
                                };
                            }
                            else if (string.IsNullOrWhiteSpace(resultDict[proc.Id].Title) || resultDict[proc.Id].Title == resultDict[proc.Id].Name)
                            {
                                resultDict[proc.Id].Title = proc.MainWindowTitle;
                            }
                        }
                    }
                    catch { }
                }
            }
            catch (Exception ex)
            {
                Log($"Aviso ao enumerar janelas ativas: {ex.Message}");
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

                if (pid <= 0)
                {
                    Log("PID inválido especificado.");
                    return false;
                }

                Log($"Iniciando captura de áudio exclusiva para PID {pid}...");

                _cts = new CancellationTokenSource();
                var startedEvent = new ManualResetEvent(false);
                bool success = false;

                _captureThread = new Thread(() =>
                {
                    RunMtaCaptureWorker(pid, startedEvent, ref success, _cts.Token);
                })
                {
                    IsBackground = true,
                    Priority = ThreadPriority.AboveNormal,
                    Name = $"ProcessAudioCapture_{pid}"
                };

                _captureThread.SetApartmentState(ApartmentState.MTA);
                _captureThread.Start();

                // Aguarda inicialização do worker MTA
                startedEvent.WaitOne(4000);

                if (success)
                {
                    IsCapturing = true;
                    CapturedPid = pid;
                    Log($"Captura de áudio para PID {pid} iniciada com sucesso no MTA!");
                    return true;
                }
                else
                {
                    Log($"Falha ao inicializar captura no worker MTA para PID {pid}.");
                    StopCapture();
                    return false;
                }
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
                        // Estéreo IEEE Float direto
                        int byteCount = numFrames * 2 * sizeof(float);
                        byte[] result = new byte[byteCount];
                        Marshal.Copy(bufferPtr, result, 0, byteCount);
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
