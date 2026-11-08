using System;
using System.Text.Json;
using System.Threading.Tasks;

namespace Xennex.Services
{
    // Ownership is retained until pending startup and cleanup finish, across all WebViews.
    public sealed class CaptureSessionService
    {
        private readonly object sync = new();
        private readonly Func<long, int, int, string, bool> startVideo;
        private readonly Func<int, bool> startAudio;
        private readonly Action stopVideo;
        private readonly Action stopAudio;
        private readonly Func<bool> audioRunning;
        private readonly Func<bool> videoRunning;
        private readonly Func<string, int, string, bool> startDesktop;
        private readonly Func<long, int, int, string, bool> startGame;
        private Task startup = Task.CompletedTask;
        private string owner;
        private string videoState = "idle";
        private string audioState = "idle";
        private bool ending;
        private bool browserVideo;
        public CaptureSessionService(Func<long, int, int, string, bool> startVideo,
            Func<int, bool> startAudio, Action stopVideo, Action stopAudio, Func<bool> audioRunning, Func<bool> videoRunning = null,
            Func<string, int, string, bool> startDesktop = null, Func<long, int, int, string, bool> startGame = null)
        {
            this.startVideo = startVideo; this.startAudio = startAudio;
            this.stopVideo = stopVideo; this.stopAudio = stopAudio; this.audioRunning = audioRunning;
            this.videoRunning = videoRunning ?? (() => true);
            this.startDesktop = startDesktop;
            this.startGame = startGame;
        }
        public bool IsBusy { get { lock (sync) return owner != null; } }
        public bool TryBegin(string requestedOwner)
        {
            if (string.IsNullOrWhiteSpace(requestedOwner) || requestedOwner.Length > 100) return false;
            lock (sync)
            {
                if (ending || (owner != null && owner != requestedOwner)) return false;
                owner = requestedOwner;
                return true;
            }
        }
        public bool BeginVideo(string requestedOwner, long hwnd, int pid, int fps, string resolution) =>
            QueueVideo(requestedOwner, () => startVideo(hwnd, pid, fps, resolution));
        public bool BeginDesktopVideo(string requestedOwner, string display, int fps, string resolution) =>
            startDesktop != null && QueueVideo(requestedOwner, () => startDesktop(display, fps, resolution));
        public bool BeginGameVideo(string requestedOwner, long hwnd, int pid, int fps, string resolution) =>
            startGame != null && QueueVideo(requestedOwner, () => startGame(hwnd, pid, fps, resolution));
        private bool QueueVideo(string requestedOwner, Func<bool> start)
        {
            lock (sync)
            {
                if (owner == null || owner != requestedOwner || ending || videoState != "idle") return false;
                videoState = "starting";
                startup = Task.Run(() => Initialize(requestedOwner, false, start));
                return true;
            }
        }
        public bool BeginBrowserVideo(string requestedOwner)
        {
            lock (sync)
            {
                if (owner == null || owner != requestedOwner || ending || videoState != "idle") return false;
                browserVideo = true; videoState = "ready";
                return true;
            }
        }
        public bool BeginAudio(string requestedOwner, int pid)
        {
            lock (sync)
            {
                if (owner == null || owner != requestedOwner || ending || videoState != "ready" || audioState != "idle") return false;
                audioState = "starting";
                startup = Task.Run(() => Initialize(requestedOwner, true, () => startAudio(pid)));
                return true;
            }
        }
        private void Initialize(string requestedOwner, bool audio, Func<bool> start)
        {
            lock (sync) { if (owner != requestedOwner || ending) return; }
            bool ready = false;
            try { ready = start(); }
            catch (Exception ex) { AppLog.Error(audio ? "CaptureSession.AudioStart" : "CaptureSession.VideoStart", ex); }
            lock (sync)
            {
                if (owner == null || owner != requestedOwner || ending) return;
                if (audio) audioState = ready ? "ready" : "error";
                else videoState = ready ? "ready" : "error";
            }
        }
        public string GetState(string requestedOwner)
        {
            lock (sync)
            {
                if (owner != requestedOwner) return JsonSerializer.Serialize(new { phase = "idle", video = "idle", audio = "idle" });
                if (!ending && !browserVideo && videoState == "ready" && !videoRunning()) videoState = "error";
                if (!ending && audioState == "ready" && !audioRunning()) audioState = "error";
                return JsonSerializer.Serialize(new { phase = ending ? "stopping" : "active", video = videoState, audio = audioState });
            }
        }
        public void StopAudio(string requestedOwner)
        {
            lock (sync)
            {
                if (owner == null || owner != requestedOwner || ending || audioState == "idle" || audioState == "error") return;
                audioState = "error";
                Task pending = startup;
                startup = Task.Run(async () =>
                {
                    await pending.ConfigureAwait(false);
                    try { stopAudio(); }
                    catch (Exception ex) { AppLog.Error("CaptureSession.Audio", ex); }
                    lock (sync) { if (owner == requestedOwner && !ending) audioState = "error"; }
                });
            }
        }
        public void End(string requestedOwner)
        {
            lock (sync)
            {
                if (owner != requestedOwner || ending) return;
                ending = true;
                Task pending = startup;
                _ = Task.Run(async () =>
                {
                    try { await pending.ConfigureAwait(false); }
                    catch (Exception ex) { AppLog.Error("CaptureSession.Startup", ex); }
                    try { stopAudio(); }
                    catch (Exception ex) { AppLog.Error("CaptureSession.Audio", ex); }
                    try { stopVideo(); }
                    catch (Exception ex) { AppLog.Error("CaptureSession.Video", ex); }
                    lock (sync)
                    {
                        owner = null; ending = false; videoState = audioState = "idle";
                        browserVideo = false;
                        startup = Task.CompletedTask;
                    }
                });
            }
        }
    }
}
