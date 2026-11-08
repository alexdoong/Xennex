using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using SharpGen.Runtime;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Xennex.Services;

namespace Xennex.CaptureWorker;

// Called serially on the capture context. Returned JPEGs own their bytes: sockets may retain them.
internal sealed class GpuFrameEncoder : IDisposable
{
    private readonly ID3D11Device device;
    private readonly ID3D11DeviceContext context;
    private readonly GpuFrameScaler scaler;
    private readonly EncoderParameters options = new(1);
    private readonly MemoryStream stream = new();
    private readonly Action<string> log;
    private ID3D11Texture2D? staging;
    private Bitmap? sized;
    private bool cpuOnly;
    internal FrameStageSample LastSample { get; private set; }
    private static readonly ImageCodecInfo Jpeg = ImageCodecInfo.GetImageEncoders().First(codec => codec.FormatID == ImageFormat.Jpeg.Guid);

    internal GpuFrameEncoder(ID3D11Device device, ID3D11DeviceContext context, int quality, Action<string> log, bool cpuOnly = false)
    {
        this.device = device; this.context = context; this.log = log; this.cpuOnly = cpuOnly;
        scaler = new GpuFrameScaler(device, context);
        options.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, (long)quality);
    }
    private static double Ms(long start) => (Stopwatch.GetTimestamp() - start) * 1000.0 / Stopwatch.Frequency;

    internal byte[] Encode(ID3D11Texture2D texture, int maxWidth, int maxHeight, ModeRotation rotation = ModeRotation.Identity)
    {
        long start = Stopwatch.GetTimestamp();
        var source = texture.Description;
        var size = FrameGeometry.Fit((int)source.Width, (int)source.Height, maxWidth, maxHeight, rotation);
        bool transform = FrameGeometry.Rotates(rotation) || size.Width != source.Width || size.Height != source.Height;
        ID3D11Texture2D readback = texture;
        string path = "none";
        if (transform && !cpuOnly)
        {
            try { readback = scaler.Transform(texture, size, rotation); path = "gpu"; }
            catch (Exception ex) when (!CaptureRecoveryPolicy.IsRecoverable(ex.HResult) &&
                ex is SharpGenException or COMException or InvalidOperationException or NotSupportedException)
            {
                cpuOnly = true;
                scaler.Dispose();
                log($"Redimensionamento GPU indisponível (0x{ex.HResult:X8}); usando CPU nesta sessão.");
            }
        }
        bool cpuTransform = transform && path != "gpu";
        if (cpuTransform) path = "cpu";
        var description = readback.Description;
        if (staging == null || staging.Description.Width != description.Width || staging.Description.Height != description.Height || staging.Description.Format != description.Format)
        {
            staging?.Dispose(); staging = null;
            description.Usage = ResourceUsage.Staging; description.BindFlags = BindFlags.None;
            description.CPUAccessFlags = CpuAccessFlags.Read; description.MiscFlags = ResourceOptionFlags.None;
            staging = device.CreateTexture2D(description);
        }
        context.CopyResource(staging, readback);
        long mapStart = Stopwatch.GetTimestamp();
        var mapped = context.Map(staging, 0, MapMode.Read, Vortice.Direct3D11.MapFlags.None);
        double mapMs = Ms(mapStart);
        try
        {
            using var raw = new Bitmap((int)description.Width, (int)description.Height, (int)mapped.RowPitch,
                PixelFormat.Format32bppRgb, mapped.DataPointer);
            using var rotated = cpuTransform && FrameGeometry.Rotates(rotation) ? (Bitmap)raw.Clone() : null;
            rotated?.RotateFlip(rotation switch
            {
                ModeRotation.Rotate90 => RotateFlipType.Rotate90FlipNone,
                ModeRotation.Rotate180 => RotateFlipType.Rotate180FlipNone,
                ModeRotation.Rotate270 => RotateFlipType.Rotate270FlipNone,
                _ => RotateFlipType.RotateNoneFlipNone,
            });
            Bitmap image = rotated ?? raw;
            if (cpuTransform && (image.Width != size.Width || image.Height != size.Height))
            {
                if (sized == null || sized.Width != size.Width || sized.Height != size.Height)
                { sized?.Dispose(); sized = new Bitmap(size.Width, size.Height, PixelFormat.Format32bppRgb); }
                using var graphics = Graphics.FromImage(sized);
                graphics.InterpolationMode = InterpolationMode.HighQualityBilinear;
                graphics.DrawImage(image, 0, 0, size.Width, size.Height);
                image = sized;
            }
            double beforeJpeg = Ms(start);
            stream.Position = 0; stream.SetLength(0);
            long jpegStart = Stopwatch.GetTimestamp();
            image.Save(stream, Jpeg, options);
            byte[] jpeg = stream.ToArray();
            LastSample = new FrameStageSample((int)source.Width, (int)source.Height, size.Width, size.Height,
                path, (long)mapped.RowPitch * description.Height, (long)source.Width * source.Height * 4,
                mapMs, beforeJpeg, Ms(jpegStart), Ms(start));
            return jpeg;
        }
        finally { context.Unmap(staging, 0); }
    }
    public void Dispose()
    { staging?.Dispose(); staging = null; sized?.Dispose(); sized = null; scaler.Dispose(); options.Dispose(); stream.Dispose(); }
}
