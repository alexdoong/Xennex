using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using Xennex.Services;

static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
static string State(CaptureSessionService session, string owner, string field)
{
    using var document = JsonDocument.Parse(session.GetState(owner));
    return document.RootElement.GetProperty(field).GetString();
}
static async Task Until(Func<bool> condition)
{
    var deadline = Stopwatch.StartNew();
    while (!condition()) { if (deadline.ElapsedMilliseconds > 5000) throw new Exception("Timed out"); await Task.Delay(10); }
}
var startup = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
int stopped = 0, audioStarts = 0;
var session = new CaptureSessionService((_, _, _, _) => { entered.SetResult(); return startup.Task.GetAwaiter().GetResult(); },
    _ => { Interlocked.Increment(ref audioStarts); return true; }, () => Interlocked.Increment(ref stopped), () => {}, () => true);
Check(!session.BeginVideo(null, 0, 0, 30, "1080p"), "No owner cannot start capture");
Check(session.TryBegin("first"), "Acquire first");
var timer = Stopwatch.StartNew();
Check(session.BeginVideo("first", 0, 0, 30, "1080p"), "Accept startup");
Check(timer.ElapsedMilliseconds < 250, "Startup must not block caller");
await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
session.End("foreign");
Check(State(session, "first", "phase") == "active", "Foreign owner cannot stop");
Check(!session.BeginAudio("first", 10), "Audio cannot precede video");
timer.Restart(); session.End("first");
Check(timer.ElapsedMilliseconds < 250, "Cancellation must not block caller");
Check(!session.TryBegin("second"), "Keep ownership during late startup");
startup.SetResult(true);
await Until(() => !session.IsBusy);
Check(stopped == 1 && audioStarts == 0, "Late startup cleaned once, no audio");
Check(session.TryBegin("second"), "Can retry after cleanup");
session.End("second"); await Until(() => !session.IsBusy);
Console.WriteLine("PASS: native startup/cancel is nonblocking; ownership protects late cleanup, foreign callers and retry");

bool running = true;
var audio = new CaptureSessionService((_, _, _, _) => true, _ => true, () => {}, () => { running = false; }, () => running);
Check(audio.TryBegin("audio") && audio.BeginVideo("audio", 0, 0, 30, "1080p"), "Start video");
await Until(() => State(audio, "audio", "video") == "ready");
Check(audio.BeginAudio("audio", 12), "Start audio");
await Until(() => State(audio, "audio", "audio") == "ready");
audio.StopAudio("foreign"); Check(running, "Foreign owner cannot stop audio");
audio.StopAudio("audio"); await Until(() => !running);
Check(State(audio, "audio", "video") == "ready", "Audio loss preserves video");
Check(State(audio, "audio", "audio") == "error", "Audio loss remains explicit");
audio.End("audio"); await Until(() => !audio.IsBusy);
Console.WriteLine("PASS: audio can fail independently and cleanup preserves owner isolation");

bool videoRunning = true;
var crashedVideo = new CaptureSessionService((_, _, _, _) => true, _ => true, () => {}, () => {}, () => true, () => videoRunning);
Check(crashedVideo.TryBegin("video") && crashedVideo.BeginVideo("video", 0, 0, 60, "1080p"), "Video accepted");
await Until(() => State(crashedVideo, "video", "video") == "ready");
videoRunning = false;
Check(State(crashedVideo, "video", "video") == "error", "Exited video worker cannot remain ready");
Check(!crashedVideo.BeginAudio("video", 12), "No audio after video worker crashed");
crashedVideo.End("video"); await Until(() => !crashedVideo.IsBusy);
Console.WriteLine("PASS: worker exit is visible before socket connection and cannot start orphan audio");

int hybridVideoStarts = 0, hybridAudioStarts = 0;
var hybrid = new CaptureSessionService((_, _, _, _) => { hybridVideoStarts++; return true; },
    _ => { hybridAudioStarts++; return true; }, () => {}, () => {}, () => true, () => false);
Check(!hybrid.BeginBrowserVideo("foreign"), "Browser video requires ownership");
Check(hybrid.TryBegin("hybrid") && hybrid.BeginBrowserVideo("hybrid"), "Reserve browser video with native audio");
Check(State(hybrid, "hybrid", "video") == "ready", "Browser video does not require WGC worker");
Check(!hybrid.TryBegin("foreign") && !hybrid.BeginVideo("hybrid", 0, 0, 60, "1080p"), "Hybrid session remains exclusive");
Check(hybrid.BeginAudio("hybrid", 12), "Native audio can accompany browser video");
await Until(() => State(hybrid, "hybrid", "audio") == "ready");
Check(hybridVideoStarts == 0 && hybridAudioStarts == 1, "No JPEG worker launched for hybrid video");
hybrid.End("hybrid"); await Until(() => !hybrid.IsBusy);
Check(hybrid.TryBegin("next-native") && hybrid.BeginVideo("next-native", 0, 0, 30, "1080p"), "Native capture after hybrid cleanup");
await Until(() => State(hybrid, "next-native", "video") == "error");
hybrid.End("next-native"); await Until(() => !hybrid.IsBusy);
Console.WriteLine("PASS: browser video and process audio share ownership without starting WGC; next native session restores health checks");

foreach (int refresh in new[] { 60, 120, 144 })
foreach (int requested in new[] { 4, 30, 60, 120 })
{
    var cadence = new CaptureFrameCadence(requested);
    int count = 0;
    for (int frame = 0; frame < refresh * 10; frame++)
    {
        double now = frame * 1000.0 / refresh + Math.Sin(frame * 1.7) * .6;
        if (cadence.ShouldCapture(now)) count++;
    }
    Check(Math.Abs(count - Math.Min(refresh, requested) * 10) <= 2, $"Cadence {refresh} Hz / {requested} FPS: {count}");
}
var stalledCadence = new CaptureFrameCadence(60);
Check(stalledCadence.ShouldCapture(0), "First frame immediate");
Check(stalledCadence.ShouldCapture(5000), "Resume after stall");
Check(!stalledCadence.ShouldCapture(5000) && !stalledCadence.ShouldCapture(double.NaN), "No burst/invalid timestamp");
Check(stalledCadence.ShouldCapture(1), "Clock reset recovers");
Console.WriteLine("PASS: 30/60/120 capture cadence tolerates refresh jitter and stalls without catch-up bursts");

foreach (uint error in new uint[] { 0x887A0026, 0x887A0005, 0x887A0007, 0x887A0022, 0x80070005 })
    Check(CaptureRecoveryPolicy.IsRecoverable(unchecked((int)error)), "Expected display transition error");
Check(!CaptureRecoveryPolicy.IsRecoverable(unchecked((int)0x887A0027)), "A static frame timeout is not a lost capture");
Check(!CaptureRecoveryPolicy.IsRecoverable(unchecked((int)0x80070057)), "Invalid API arguments must fail, not loop forever");
var recovery = new CaptureRecoveryPolicy();
Check(recovery.CanRetry(100) && recovery.CanRetry(15099), "Recovery has a bounded grace period");
Check(!recovery.CanRetry(15100), "Recovery must eventually stop");
recovery.FrameReceived(); Check(recovery.CanRetry(16000), "Actual frames reset recovery budget");
Check(!recovery.CanRetry(double.NaN), "Invalid recovery timestamp rejected");
int desktopStarts = 0;
var desktopSession = new CaptureSessionService((_, _, _, _) => throw new Exception("Must not start WGC"), _ => true,
    () => {}, () => {}, () => true, () => true, (monitor, fps, resolution) => { desktopStarts++; return monitor == "chosen" && fps == 60 && resolution == "1080p"; });
Check(!desktopSession.BeginDesktopVideo("foreign", "chosen", 60, "1080p"), "DXGI needs ownership");
Check(desktopSession.TryBegin("desktop") && desktopSession.BeginDesktopVideo("desktop", "chosen", 60, "1080p"), "Queue selected monitor");
await Until(() => State(desktopSession, "desktop", "video") == "ready");
Check(desktopStarts == 1 && !desktopSession.TryBegin("foreign"), "DXGI shares the same exclusive native session");
desktopSession.End("desktop"); await Until(() => !desktopSession.IsBusy);
Console.WriteLine("PASS: selected-monitor DXGI is owner-scoped; mode-change recovery is bounded and silence is not failure");

int gameStarts = 0;
var gameSession = new CaptureSessionService((_, _, _, _) => throw new Exception("Game cannot become window/monitor capture"), _ => true,
    () => {}, () => {}, () => true, startGame: (hwnd, pid, fps, resolution) => {
        Check(hwnd == 456 && pid == 789 && fps == 120 && resolution == "1080p", "Selected game identity and quality retained"); gameStarts++; return true;
    });
Check(!gameSession.BeginGameVideo("foreign", 456, 789, 120, "1080p"), "Game needs ownership before loading a hook");
Check(gameSession.TryBegin("game") && gameSession.BeginGameVideo("game", 456, 789, 120, "1080p"), "Explicit game start accepted");
await Until(() => State(gameSession, "game", "video") == "ready");
Check(gameStarts == 1 && !gameSession.TryBegin("foreign") && !gameSession.BeginGameVideo("game", 456, 789, 120, "1080p"), "One exclusive game startup");
gameSession.End("game"); await Until(() => !gameSession.IsBusy);
Check(!session.BeginGameVideo("second", 456, 789, 120, "1080p"), "Absent game backend cannot silently fallback");
Console.WriteLine("PASS: game hook is opt-in, owner-scoped and preserves selected PID/HWND/quality without fallback");

using var converter = new ProcessAudioCaptureService();
var method = typeof(ProcessAudioCaptureService).GetMethod("ConvertToStereoFloat32", BindingFlags.NonPublic | BindingFlags.Instance);
float[] samples = { .8f, -.8f, .99f, -.99f };
IntPtr buffer = Marshal.AllocHGlobal(samples.Length * sizeof(float));
try
{
    Marshal.Copy(samples, 0, buffer, samples.Length);
    var bytes = (byte[])method.Invoke(converter, new object[] { buffer, 2, 2, 32, true });
    float[] actual = new float[samples.Length]; Buffer.BlockCopy(bytes, 0, actual, 0, bytes.Length);
    Check(samples.SequenceEqual(actual), "Float32 source amplitude must survive without forced gain/clipping");
}
finally { Marshal.FreeHGlobal(buffer); }
Console.WriteLine("PASS: real audio converter preserves stereo amplitudes; no audio hardware used");
