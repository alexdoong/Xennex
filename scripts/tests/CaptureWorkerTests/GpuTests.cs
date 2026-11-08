using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text.Json;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Xennex.CaptureWorker;

internal static class GpuTests
{
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    internal static void Pure()
    {
        Check(FrameGeometry.Fit(3840, 2160, 1920, 1080, ModeRotation.Identity) == new FrameSize(1920, 1080), "4K fits Full HD");
        Check(FrameGeometry.Fit(640, 480, 1920, 1080, ModeRotation.Identity) == new FrameSize(640, 480), "Never upscale");
        Check(FrameGeometry.Fit(641, 481, 1920, 1080, ModeRotation.Rotate90) == new FrameSize(480, 640), "Rotated even geometry");
        var telemetry = new CaptureTelemetry();
        var sample = new FrameStageSample(3840, 2160, 1920, 1080, "gpu", 8294400, 33177600, 2, 3, 4, 7);
        for (int i = 0; i <= 120; i++) telemetry.Add(sample, i * (2000.0 / 120));
        using var report = JsonDocument.Parse(telemetry.Snapshot);
        Check(Math.Abs(report.RootElement.GetProperty("processedFps").GetDouble() - 60) < .01, "Window FPS uses elapsed time");
        Check(report.RootElement.GetProperty("p95Ms").GetDouble() == 7, "Bounded timing percentile");
        telemetry = new CaptureTelemetry();
        for (int i = 0; i < 256; i++) telemetry.Add(sample, i);
        Check(telemetry.Snapshot.Length is > 0 and < 2000, "High-rate measurements remain bounded");
        Console.WriteLine("PASS: frame geometry and bounded pipeline measurements; no GPU or screen used");
    }
    internal static void Run()
    {
        D3D11.D3D11CreateDevice(null, DriverType.Hardware, DeviceCreationFlags.BgraSupport,
            new[] { FeatureLevel.Level_11_0 }, out ID3D11Device device, out ID3D11DeviceContext context).CheckError();
        using (device) using (context)
        using (var gpu = new GpuFrameEncoder(device, context, 95, Console.WriteLine))
        using (var cpu = new GpuFrameEncoder(device, context, 95, Console.WriteLine, cpuOnly: true))
        {
            // Same generated pixels are processed by both paths; no window or monitor is captured.
            using var small = Texture(device, context, 640, 480);
            foreach (var rotation in new[] { ModeRotation.Identity, ModeRotation.Rotate90, ModeRotation.Rotate180, ModeRotation.Rotate270 })
            {
                byte[] actual = gpu.Encode(small, 320, 320, rotation);
                byte[] expected = cpu.Encode(small, 320, 320, rotation);
                Compare(actual, expected);
                Check(gpu.LastSample.ScalePath == "gpu", "GPU path actually executed");
                Check(gpu.LastSample.MappedBytes < gpu.LastSample.SourceBytes, "Reduced readback");
            }
            byte[] first = gpu.Encode(small, 320, 240); byte[] saved = first.ToArray();
            gpu.Encode(small, 160, 120);
            Check(first.SequenceEqual(saved), "Previously queued JPEG cannot be overwritten");
            using var odd = Texture(device, context, 641, 481);
            Compare(gpu.Encode(odd, 320, 240), cpu.Encode(odd, 320, 240));
            using var checker = Texture(device, context, 640, 480, pattern: 1);
            using var reduced = Image(gpu.Encode(checker, 320, 240));
            var gray = reduced.GetPixel(90, 90);
            Check(gray.R is > 115 and < 140 && Math.Abs(gray.R - gray.G) < 3, "Area sampling avoids checkerboard aliasing");
            using var gradient = Texture(device, context, 640, 480, pattern: 2);
            Compare(gpu.Encode(gradient, 320, 240), cpu.Encode(gradient, 320, 240));
            using var native = Image(gpu.Encode(small, 1920, 1080));
            Check(native.Width == 640 && native.Height == 480 && gpu.LastSample.ScalePath == "none", "No resize skips the shader");

            using var large = Texture(device, context, 3840, 2160);
            Compare(gpu.Encode(large, 1920, 1080), cpu.Encode(large, 1920, 1080));
            for (int i = 0; i < 4; i++) { cpu.Encode(large, 1920, 1080); gpu.Encode(large, 1920, 1080); }
            var cpuTimes = new List<double>(); var gpuTimes = new List<double>();
            for (int i = 0; i < 24; i++)
            {
                // Alternate order to reduce thermal/order bias.
                if (i % 2 == 0) { cpu.Encode(large, 1920, 1080); cpuTimes.Add(cpu.LastSample.TotalMs); gpu.Encode(large, 1920, 1080); gpuTimes.Add(gpu.LastSample.TotalMs); }
                else { gpu.Encode(large, 1920, 1080); gpuTimes.Add(gpu.LastSample.TotalMs); cpu.Encode(large, 1920, 1080); cpuTimes.Add(cpu.LastSample.TotalMs); }
            }
            Console.WriteLine($"BENCH 4K→1080p, JPEG95, generated quadrants: CPU mean={cpuTimes.Average():F2}ms p95={Percentile(cpuTimes):F2}ms; GPU mean={gpuTimes.Average():F2}ms p95={Percentile(gpuTimes):F2}ms; mapped CPU={cpu.LastSample.MappedBytes} GPU={gpu.LastSample.MappedBytes} bytes/frame");
        }
        // Feature level 10 cannot run cs_5_0: exercise the actual unsupported-shader fallback.
        D3D11.D3D11CreateDevice(null, DriverType.Warp, DeviceCreationFlags.BgraSupport,
            new[] { FeatureLevel.Level_10_0 }, out ID3D11Device oldDevice, out ID3D11DeviceContext oldContext).CheckError();
        using (oldDevice) using (oldContext)
        using (var fallback = new GpuFrameEncoder(oldDevice, oldContext, 90, Console.WriteLine))
        using (var texture = Texture(oldDevice, oldContext, 640, 480))
        {
            using var image = Image(fallback.Encode(texture, 320, 240));
            Check(fallback.LastSample.ScalePath == "cpu" && image.Width == 320 && image.GetPixel(80, 60).R > 180, "Unsupported GPU falls back with correct pixels");
        }
        Console.WriteLine("PASS: GPU RGB, 4 rotations, odd dimensions, repeated resize, no upscale, immutable JPEGs and CPU fallback; generated textures only");
    }
    private static double Percentile(List<double> values) => values.Order().ElementAt((int)Math.Ceiling(values.Count * .95) - 1);
    private static Bitmap Image(byte[] bytes)
    { using var stream = new MemoryStream(bytes); using var image = new Bitmap(stream); return new Bitmap(image); }
    private static void Compare(byte[] actual, byte[] expected)
    {
        using var a = Image(actual); using var b = Image(expected);
        Check(a.Size == b.Size, "Output geometry matches CPU");
        foreach (var (x, y) in new[] { (1, 1), (3, 1), (1, 3), (3, 3) })
        {
            Color c = a.GetPixel(a.Width * x / 4, a.Height * y / 4), d = b.GetPixel(b.Width * x / 4, b.Height * y / 4);
            Check(Math.Abs(c.R - d.R) < 12 && Math.Abs(c.G - d.G) < 12 && Math.Abs(c.B - d.B) < 12, "Channels and orientation match CPU");
        }
    }
    private static ID3D11Texture2D Texture(ID3D11Device device, ID3D11DeviceContext context, int width, int height, int pattern = 0)
    {
        var pixels = new int[width * height];
        for (int y = 0; y < height; y++) for (int x = 0; x < width; x++)
        {
            uint rgb = pattern == 1 ? ((x + y) % 2 == 0 ? 0u : 0xFFFFFFu) : pattern == 2
                ? (uint)((x * 255 / width << 16) | (y * 255 / height << 8) | 80)
                : x < width / 2 ? y < height / 2 ? 0xEF2010u : 0x1030E0u : y < height / 2 ? 0x20D030u : 0xE0C020u;
            pixels[y * width + x] = unchecked((int)(0xFF000000u | rgb));
        }
        var texture = device.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.B8G8R8A8_UNorm, SampleDescription = new SampleDescription(1, 0), Usage = ResourceUsage.Default,
        });
        var pinned = GCHandle.Alloc(pixels, GCHandleType.Pinned);
        try { context.UpdateSubresource(texture, 0, null, pinned.AddrOfPinnedObject(), (uint)width * 4, 0); }
        catch { texture.Dispose(); throw; }
        finally { pinned.Free(); }
        return texture;
    }
}
