using System;
namespace Xennex.Services
{
    // Monotonic, time-based easing. Reversals start at the current rendered position.
    public sealed class CompactMotion
    {
        private double start = 1, target = 1;
        private long started;
        private double duration = 220;
        public void Reset(long now) { start = target = 1; started = now; }
        public double Update(bool show, long now, bool animate)
        {
            double current = Sample(now);
            double next = show ? 1 : 0;
            if (!animate) { start = target = next; started = now; return next; }
            if (next != target)
            {
                start = current; target = next; started = now;
                duration = Math.Max(80, 240 * Math.Abs(target - start));
            }
            return Sample(now);
        }
        public bool IsMoving(long now) => start != target && now - started < duration;

        private double Sample(long now)
        {
            double t = Math.Clamp((now - started) / duration, 0, 1);
            double eased = t * t * (3 - 2 * t);
            return start + (target - start) * eased;
        }
    }
}
