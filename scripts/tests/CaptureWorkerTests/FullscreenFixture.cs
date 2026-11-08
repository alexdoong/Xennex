using System.Diagnostics;
using System.Drawing;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Vortice.Mathematics;
using Xennex.CaptureWorker;

// Opt-in interactive test. Only generated red/blue frames are inspected; nothing is saved.
internal sealed class FullscreenFixture : Form
{
    private ID3D11Device? device;
    private ID3D11DeviceContext? context;
    private IDXGISwapChain1? swap;
    private ID3D11RenderTargetView? target;
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 16 };
    private readonly Stopwatch elapsed = new();
    private Task capture = Task.CompletedTask;
    private volatile bool running;
    private int phase, redFrames, blueFrames, recovering;
    private bool leftFullscreen, reenteredFullscreen;
    private Exception? failure;
    private string? worker;
    private readonly CancellationTokenSource stop = new();

    internal static void Run(string? worker = null)
    {
        using var window = new FullscreenFixture { worker = worker, Text = "Xennex · teste fullscreen sintético", Width = 800, Height = 600, StartPosition = FormStartPosition.CenterScreen };
        Application.Run(window);
        if (window.failure != null) throw new Exception("Fullscreen fixture failed", window.failure);
        if (window.redFrames < 2 || window.blueFrames < 2) throw new Exception($"Exclusive capture did not resume: red={window.redFrames}, blue={window.blueFrames}");
        Console.WriteLine($"PASS: actual DXGI exclusive/windowed/exclusive transitions; red={window.redFrames}, blue={window.blueFrames}, recovery events={window.recovering}; no frames saved");
    }
    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        try
        {
            D3D11.D3D11CreateDevice(null, DriverType.Hardware, DeviceCreationFlags.BgraSupport,
                new[] { FeatureLevel.Level_11_0 }, out device, out context).CheckError();
            using var factory = Vortice.DXGI.DXGI.CreateDXGIFactory1<IDXGIFactory2>();
            swap = factory.CreateSwapChainForHwnd(device, Handle, new SwapChainDescription1
            {
                Width = (uint)ClientSize.Width, Height = (uint)ClientSize.Height, Format = Format.B8G8R8A8_UNorm,
                BufferCount = 2, BufferUsage = Usage.RenderTargetOutput, SampleDescription = new SampleDescription(1, 0),
                SwapEffect = SwapEffect.FlipDiscard, Flags = SwapChainFlags.AllowModeSwitch,
            });
            Switch(true); phase = 1;
            using var output = swap.GetContainingOutput(); string display = output.Description.DeviceName;
            running = true;
            Action<byte[]> inspect = bytes =>
                {
                    int expected = Volatile.Read(ref phase); if (expected == 0) return;
                    using var stream = new MemoryStream(bytes); using var image = new Bitmap(stream);
                    System.Drawing.Color color = image.GetPixel(image.Width / 2, image.Height / 2);
                    if (expected == 1 && color.R > 150 && color.B < 90) Interlocked.Increment(ref redFrames);
                    if (expected == 2 && color.B > 150 && color.R < 90) Interlocked.Increment(ref blueFrames);
                };
            Action<string> status = state => { if (state == "recovering") Interlocked.Increment(ref recovering); };
            capture = worker == null
                ? Task.Run(() => DesktopDuplicationCapture.RunAsync(display, 30, 640, 360, 80, () => running, () => true, inspect, status, _ => {}))
                : Task.Run(() => WorkerStreamFixture.Run(worker, display, inspect, status, stop.Token));
            timer.Tick += Render; elapsed.Start(); timer.Start();
        }
        catch (Exception ex) { failure = ex; Close(); }
    }
    private void Switch(bool fullscreen)
    {
        target?.Dispose(); target = null; context!.ClearState(); context.Flush();
        swap!.SetFullscreenState(fullscreen, null).CheckError();
        swap.GetFullscreenState(out var active, out var output).CheckError(); output?.Dispose();
        if ((bool)active != fullscreen) throw new Exception("Exclusive mode was not confirmed by DXGI");
        swap.ResizeBuffers(0, 0, 0, Format.Unknown, SwapChainFlags.AllowModeSwitch).CheckError();
        using var buffer = swap.GetBuffer<ID3D11Texture2D>(0); target = device!.CreateRenderTargetView(buffer);
    }
    private void Render(object? sender, EventArgs e)
    {
        try
        {
            if (capture.IsFaulted) { capture.GetAwaiter().GetResult(); }
            if (!leftFullscreen && elapsed.ElapsedMilliseconds > 1800) { phase = 0; Switch(false); leftFullscreen = true; }
            if (!reenteredFullscreen && elapsed.ElapsedMilliseconds > 3000) { Switch(true); phase = 2; reenteredFullscreen = true; }
            if (elapsed.ElapsedMilliseconds > 5500) { Close(); return; }
            context!.ClearRenderTargetView(target!, phase == 2 ? new Color4(.1f, .15f, .9f, 1) : new Color4(.9f, .1f, .1f, 1));
            swap!.Present(1, PresentFlags.None).CheckError();
        }
        catch (Exception ex) { failure = ex; Close(); }
    }
    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        timer.Stop(); timer.Dispose(); phase = 0; running = false; stop.Cancel();
        try { capture.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult(); }
        catch (Exception ex) { failure ??= ex; }
        target?.Dispose();
        try { swap?.SetFullscreenState(false, null); } catch { }
        swap?.Dispose(); context?.Dispose(); device?.Dispose();
        stop.Dispose();
        base.OnFormClosed(e);
    }
}
