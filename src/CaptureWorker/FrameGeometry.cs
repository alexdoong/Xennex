using System;
using Vortice.DXGI;

namespace Xennex.CaptureWorker;

internal readonly record struct FrameSize(int Width, int Height);
internal static class FrameGeometry
{
    internal static FrameSize Fit(int width, int height, int maxWidth, int maxHeight, ModeRotation rotation)
    {
        if (width < 2 || height < 2 || width > 16384 || height > 16384) throw new ArgumentOutOfRangeException(nameof(width));
        if (rotation is ModeRotation.Rotate90 or ModeRotation.Rotate270) (width, height) = (height, width);
        double scale = maxWidth > 0 && maxHeight > 0 ? Math.Min(1, Math.Min((double)maxWidth / width, (double)maxHeight / height)) : 1;
        return new FrameSize(Math.Max(2, (int)(width * scale) / 2 * 2), Math.Max(2, (int)(height * scale) / 2 * 2));
    }
    internal static bool Rotates(ModeRotation rotation) => rotation is ModeRotation.Rotate90 or ModeRotation.Rotate180 or ModeRotation.Rotate270;
}
