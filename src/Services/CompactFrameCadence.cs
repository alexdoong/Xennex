using System;

namespace Xennex.Services
{
    // Limits render callbacks without accumulating missed frames or changing motion duration.
    public sealed class CompactFrameCadence
    {
        private double nextFrame;
        private int previousFps = -1;
        public void Reset() { nextFrame = 0; previousFps = -1; }
        public bool ShouldRender(double nowMilliseconds, int fps)
        {
            if (fps != previousFps) { nextFrame = nowMilliseconds; previousFps = fps; }
            if (fps <= 0) return true;
            if (nowMilliseconds + 0.1 < nextFrame) return false;
            double period = 1000.0 / fps;
            nextFrame += (Math.Floor(Math.Max(0, nowMilliseconds + 0.1 - nextFrame) / period) + 1) * period;
            return true;
        }
    }
}
