using System.Collections.Generic;

namespace Xennex.CaptureWorker;

// One successful initial frame must not make an endless recreate/lost loop look healthy.
internal sealed class CaptureRestartGuard
{
    private readonly Queue<double> losses = new();
    internal bool Unstable => losses.Count >= 3;
    internal bool Lost(double nowMs)
    {
        while (losses.Count > 0 && nowMs - losses.Peek() > 10000) losses.Dequeue();
        if (losses.Count < 6) losses.Enqueue(nowMs);
        return losses.Count < 6;
    }
    internal void Stable() => losses.Clear();
}
