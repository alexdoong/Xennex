using System;

namespace Xennex.Services
{
    // Keep the deadline's phase instead of accumulating callback jitter. No catch-up bursts.
    public sealed class CaptureFrameCadence
    {
        private double nextFrame = double.NaN;
        private double previousTime = double.NaN;
        private readonly double period;
        private readonly double tolerance;

        public CaptureFrameCadence(int fps)
        {
            period = 1000.0 / Math.Clamp(fps, 1, 120);
            tolerance = Math.Min(2.0, period * .2);
        }

        public bool ShouldCapture(double nowMs)
        {
            if (!double.IsFinite(nowMs)) return false;
            if (double.IsNaN(nextFrame) || nowMs < previousTime) nextFrame = nowMs;
            previousTime = nowMs;
            if (nowMs + tolerance < nextFrame) return false;
            nextFrame += (Math.Floor(Math.Max(0, nowMs + tolerance - nextFrame) / period) + 1) * period;
            return true;
        }
    }
}
