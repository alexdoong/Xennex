using System;

namespace Xennex.Services
{
    // All WebView windows share this owner gate through the same ApiBridge instance.
    public sealed class CaptureSessionService
    {
        private readonly object sync = new();
        private readonly StreamService video;
        private readonly ProcessAudioCaptureService audio;
        private string owner;
        public CaptureSessionService(StreamService video, ProcessAudioCaptureService audio)
        {
            this.video = video;
            this.audio = audio;
        }
        public bool TryBegin(string requestedOwner)
        {
            if (string.IsNullOrWhiteSpace(requestedOwner) || requestedOwner.Length > 100) return false;
            lock (sync)
            {
                if (owner != null && owner != requestedOwner) return false;
                owner = requestedOwner;
                return true;
            }
        }
        public void End(string requestedOwner)
        {
            lock (sync)
            {
                if (owner != requestedOwner) return;
                try { video.StopNativeCapture(); }
                catch (Exception ex) { AppLog.Error("CaptureSession.Video", ex); }
                try { audio.StopCapture(); }
                catch (Exception ex) { AppLog.Error("CaptureSession.Audio", ex); }
                owner = null;
            }
        }
    }
}
