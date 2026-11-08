using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using SharpGen.Runtime;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Xennex.Services;

namespace Xennex.CaptureWorker;

// Monitor-only: never used as an automatic fallback for a window capture.
internal static class DesktopDuplicationCapture
{
    internal interface ISource : IDisposable
    {
        long AdapterId { get; }
        string MonitorIdentity { get; }
        void Next(Func<bool> shouldCapture, Action<byte[]> publish);
    }
    internal static async Task RunAsync(string display, int fps, int maxWidth, int maxHeight, int quality,
        Func<bool> running, Func<bool> hasClients, Action<byte[]> publish, Action<string> status, Action<string> log,
        Func<string, long?, ISource>? open = null, Func<Task>? retryDelay = null, Func<double>? clock = null,
        Action<FrameStageSample>? measure = null)
    {
        var cadence = new CaptureFrameCadence(fps);
        var idle = new CaptureFrameCadence(4);
        var recovery = new CaptureRecoveryPolicy();
        var restarts = new CaptureRestartGuard();
        bool everReceived = false;
        open ??= (name, adapter) => Open(name, adapter, maxWidth, maxHeight, quality, log, measure);
        retryDelay ??= () => Task.Delay(500);
        clock ??= () => Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency;
        long? adapterId = null;
        string? monitorIdentity = null;
        status("recovering");
        while (running())
        {
            try
            {
                using var capture = open(display, adapterId);
                if (adapterId.HasValue && capture.AdapterId != adapterId.Value) throw new InvalidOperationException("A placa do monitor selecionado mudou; selecione o monitor novamente.");
                if (monitorIdentity != null && !string.Equals(capture.MonitorIdentity, monitorIdentity, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("A identidade do monitor selecionado mudou; selecione o monitor novamente.");
                adapterId ??= capture.AdapterId;
                monitorIdentity ??= capture.MonitorIdentity;
                log($"DXGI conectado ao monitor selecionado: {display}");
                double openedAt = clock();
                bool receivedSinceOpen = false;
                if (!recovery.CanRetry(clock())) throw new InvalidOperationException("O monitor selecionado não voltou a produzir imagens.");
                while (running())
                {
                    capture.Next(() =>
                    {
                        double now = clock();
                        return (hasClients() || idle.ShouldCapture(now)) && cadence.ShouldCapture(now);
                    }, frame =>
                    {
                        receivedSinceOpen = true; everReceived = true; recovery.FrameReceived();
                        status(restarts.Unstable ? "unstable" : "ready"); publish(frame);
                    });
                    if (receivedSinceOpen && clock() - openedAt >= 2000)
                    { restarts.Stable(); status("ready"); }
                    if (!receivedSinceOpen && !recovery.CanRetry(clock()))
                        throw new InvalidOperationException("O monitor selecionado não voltou a produzir imagens.");
                }
            }
            catch (Exception ex) when (CaptureRecoveryPolicy.IsRecoverable(ex.HResult))
            {
                bool canRestart = !everReceived || restarts.Lost(clock());
                status(restarts.Unstable ? "unstable" : "recovering");
                if (!canRestart)
                {
                    // Give the serialized local status sender one bounded retry interval before closing.
                    await retryDelay();
                    throw new InvalidOperationException("O Windows invalida esta captura repetidamente. Tente o jogo em janela/sem bordas ou outra fonte; não foi selecionado outro monitor.", ex);
                }
                if (!recovery.CanRetry(clock()))
                    throw new InvalidOperationException("A captura DXGI não recuperou o monitor selecionado a tempo.", ex);
                log($"DXGI temporariamente indisponível (0x{ex.HResult:X8}); recriando a mesma saída.");
                await retryDelay();
            }
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct DisplayDevice
    {
        public int Size;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Name;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Description;
        public uint Flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Id;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Key;
    }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool EnumDisplayDevices(string device, uint index, ref DisplayDevice description, uint flags);

    private static string GetMonitorIdentity(string display)
    {
        var description = new DisplayDevice { Size = Marshal.SizeOf<DisplayDevice>() };
        if (!EnumDisplayDevices(display, 0, ref description, 1) || string.IsNullOrWhiteSpace(description.Id))
            throw new InvalidOperationException("Não foi possível confirmar a identidade do monitor selecionado.");
        return description.Id;
    }

    private static Session Open(string display, long? adapterId, int maxWidth, int maxHeight, int quality, Action<string> log, Action<FrameStageSample>? measure)
    {
        using var factory = Vortice.DXGI.DXGI.CreateDXGIFactory1<IDXGIFactory1>();
        for (uint index = 0; factory.EnumAdapters1(index, out var adapter).Success; index++)
        {
            using (adapter)
            {
                if (adapterId.HasValue && adapter.Description1.Luid != adapterId.Value) continue;
                for (uint outputIndex = 0; adapter.EnumOutputs(outputIndex, out var output).Success; outputIndex++)
                {
                    using (output)
                    {
                        var description = output.Description;
                        if (!description.AttachedToDesktop || !string.Equals(description.DeviceName, display, StringComparison.OrdinalIgnoreCase)) continue;
                        return new Session(adapter, output, description.Rotation, maxWidth, maxHeight, quality, log, measure);
                    }
                }
            }
        }
        throw new System.Runtime.InteropServices.COMException("O monitor selecionado está temporariamente desconectado.", unchecked((int)0x887A0026));
    }

    private sealed class Session : ISource
    {
        private readonly ID3D11Device device;
        private readonly ID3D11DeviceContext context;
        private readonly IDXGIOutputDuplication duplication;
        private readonly GpuFrameEncoder encoder;
        private readonly Action<FrameStageSample>? measure;
        private readonly ModeRotation rotation;
        private readonly int maxWidth, maxHeight;
        public long AdapterId { get; }
        public string MonitorIdentity { get; }

        internal Session(IDXGIAdapter1 adapter, IDXGIOutput output, ModeRotation rotation, int maxWidth, int maxHeight, int quality, Action<string> log, Action<FrameStageSample>? measure)
        {
            this.rotation = rotation;
            MonitorIdentity = GetMonitorIdentity(output.Description.DeviceName);
            this.maxWidth = maxWidth; this.maxHeight = maxHeight; this.measure = measure;
            AdapterId = adapter.Description1.Luid;
            D3D11.D3D11CreateDevice(adapter, DriverType.Unknown, DeviceCreationFlags.BgraSupport,
                new[] { FeatureLevel.Level_11_0 }, out device, out context).CheckError();
            try
            {
                using var output1 = output.QueryInterface<IDXGIOutput1>();
                duplication = output1.DuplicateOutput(device);
                try { encoder = new GpuFrameEncoder(device, context, quality, log); }
                catch { duplication.Dispose(); throw; }
            }
            catch { context.Dispose(); device.Dispose(); throw; }
        }

        public void Next(Func<bool> shouldCapture, Action<byte[]> publish)
        {
            var result = duplication.AcquireNextFrame(100, out _, out var resource);
            if (result.Code == unchecked((int)0x887A0027)) return; // A static image is not a failure.
            result.CheckError();
            try
            {
                using (resource)
                using (var texture = resource.QueryInterface<ID3D11Texture2D>())
                    if (shouldCapture())
                    {
                        byte[] jpeg = encoder.Encode(texture, maxWidth, maxHeight, rotation);
                        measure?.Invoke(encoder.LastSample); publish(jpeg);
                    }
            }
            finally { duplication.ReleaseFrame().CheckError(); }
        }

        public void Dispose() { encoder.Dispose(); duplication.Dispose(); context.Dispose(); device.Dispose(); }
    }
}
