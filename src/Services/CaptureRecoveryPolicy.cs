using System;

namespace Xennex.Services
{
    public sealed class CaptureRecoveryPolicy
    {
        private double failedSince = double.NaN;
        public const int TimeoutMs = 15000;
        public static bool IsRecoverable(int code) => code is
            unchecked((int)0x887A0026) or // Access lost after fullscreen/desktop switch.
            unchecked((int)0x887A0005) or // Device removed.
            unchecked((int)0x887A0007) or // Device reset.
            unchecked((int)0x887A0022) or // Duplication temporarily unavailable.
            unchecked((int)0x80070005);   // Secure desktop; never bypass it.

        public bool CanRetry(double nowMs)
        {
            if (!double.IsFinite(nowMs)) return false;
            if (double.IsNaN(failedSince)) failedSince = nowMs;
            return nowMs >= failedSince && nowMs - failedSince < TimeoutMs;
        }
        public void FrameReceived() => failedSince = double.NaN;
    }
}
