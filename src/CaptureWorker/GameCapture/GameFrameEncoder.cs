using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;

namespace Xennex.CaptureWorker;

internal sealed class GameFrameEncoder : IDisposable
{
    readonly EncoderParameters options = new(1);
    readonly MemoryStream stream = new();
    static readonly ImageCodecInfo Jpeg = ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);
    Bitmap? sized;
    internal FrameStageSample LastSample { get; private set; }
    internal GameFrameEncoder(int quality) => options.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, (long)Math.Clamp(quality, 1, 100));
    internal unsafe byte[] Encode(GameFrame frame, int maxWidth, int maxHeight)
    {
        long start = Stopwatch.GetTimestamp();
        int count = NativeGameSession.ValidateFrame(frame.Width, frame.Height, frame.Width * 4, 1);
        if (frame.Pixels.Length != count) throw new InvalidDataException("Invalid game pixel buffer");
        var size = FrameGeometry.Fit(frame.Width, frame.Height, maxWidth, maxHeight, Vortice.DXGI.ModeRotation.Identity);
        fixed (byte* pointer = frame.Pixels)
        {
            // OpenGL is bottom-up. Negative stride presents top-down without a flip copy.
            using var raw = new Bitmap(frame.Width, frame.Height, -frame.Width * 4, PixelFormat.Format32bppRgb, new IntPtr(pointer + (frame.Height - 1) * frame.Width * 4));
            Bitmap image = raw;
            bool scale = size.Width != frame.Width || size.Height != frame.Height;
            if (scale)
            {
                if (sized == null || sized.Width != size.Width || sized.Height != size.Height) { sized?.Dispose(); sized = new Bitmap(size.Width, size.Height, PixelFormat.Format32bppRgb); }
                using var graphics = Graphics.FromImage(sized);
                graphics.InterpolationMode = InterpolationMode.HighQualityBilinear;
                graphics.DrawImage(raw, 0, 0, size.Width, size.Height); image = sized;
            }
            long jpegStart = Stopwatch.GetTimestamp(); stream.Position = 0; stream.SetLength(0);
            image.Save(stream, Jpeg, options); var result = stream.ToArray();
            double ms = 1000.0 / Stopwatch.Frequency;
            LastSample = new FrameStageSample(frame.Width, frame.Height, size.Width, size.Height, scale ? "cpu" : "none", count, count,
                0, (jpegStart - start) * ms, (Stopwatch.GetTimestamp() - jpegStart) * ms, (Stopwatch.GetTimestamp() - start) * ms);
            return result;
        }
    }
    public void Dispose() { sized?.Dispose(); stream.Dispose(); options.Dispose(); }
}
