using System.Runtime.InteropServices;
using Xennex.CaptureWorker;

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        if (args.Contains("--game-worker"))
        {
            int native = Array.IndexOf(args, "--native-directory"), worker = Array.IndexOf(args, "--worker");
            if (native < 0 || worker < 0) throw new ArgumentException("--game-worker requires --native-directory and --worker");
            GameWorkerTests.Run(args[worker + 1], args[native + 1]).GetAwaiter().GetResult(); return;
        }
        if (args.Contains("--verify-game-hook"))
        {
            int option = Array.IndexOf(args, "--native-directory");
            if (option < 0) throw new ArgumentException("--verify-game-hook requires --native-directory");
            OsuGameHookProbe.VerifyBinaries(args[option + 1]); Console.WriteLine("PASS game capture publisher and binary integrity"); return;
        }
        if (args.Contains("--osu-game-hook"))
        {
            int option = Array.IndexOf(args, "--native-directory");
            if (option < 0 || !args.Contains("--authorize-game-hook")) throw new ArgumentException("Real game hook requires explicit --authorize-game-hook and --native-directory");
            OsuGameHookProbe.Run(args[option + 1]).GetAwaiter().GetResult(); return;
        }
        if (args.Contains("--game-hook"))
        {
            int option = Array.IndexOf(args, "--native-directory");
            if (option < 0) throw new ArgumentException("--game-hook requires --native-directory with own prototype binaries.");
            GameHookTests.Run(args[option + 1]).GetAwaiter().GetResult(); return;
        }
        if (args.Contains("--gpu")) { GpuTests.Run(); return; }
        if (args.Contains("--osu"))
        {
            int option = Array.IndexOf(args, "--worker");
            if (option < 0) throw new ArgumentException("--osu exige --worker com caminho explícito.");
            OsuCaptureProbe.Run(args[option + 1], args.Contains("--wgc")).GetAwaiter().GetResult(); return;
        }
        if (args.Contains("--fullscreen"))
        {
            int workerOption = Array.IndexOf(args, "--worker");
            FullscreenFixture.Run(workerOption >= 0 ? args[workerOption + 1] : null); return;
        }
        Verify().GetAwaiter().GetResult();
    }
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static async Task Verify()
    {
        GameFrameTests.Run();
        GpuTests.Pure();
        await SocketTests.Run();
        double repeatedClock = 0; int repeatedFrames = 0, repeatedOpened = 0;
        var repeatedPhases = new List<string>();
        try
        {
            await DesktopDuplicationCapture.RunAsync("repeated-one-frame", 60, 0, 0, 88, () => true, () => true,
                _ => repeatedFrames++, repeatedPhases.Add, _ => {}, (_, _) =>
                {
                    repeatedOpened++; bool sent = false;
                    return new FakeSource(7, (ready, publish) =>
                    {
                        if (sent) throw new COMException("access lost after one frame", unchecked((int)0x887A0026));
                        sent = true; if (ready()) publish(new byte[] { 1 });
                    }, () => {});
                }, () => { repeatedClock += 500; return Task.CompletedTask; }, () => repeatedClock);
            throw new Exception("One frame per restart must not reset failure forever");
        }
        catch (InvalidOperationException ex)
        {
            Check(repeatedOpened == 6 && repeatedFrames == 6 && repeatedClock == 3000 && repeatedPhases.Contains("unstable"), "Repeated single-frame loss is bounded and visible");
            Check(ex.Message.Contains("sem bordas"), "Fatal instability explains manual alternatives");
        }
        var guard = new CaptureRestartGuard();
        Check(guard.Lost(0) && guard.Lost(500) && guard.Lost(1000) && guard.Unstable, "Burst becomes unstable");
        guard.Stable(); Check(!guard.Unstable && guard.Lost(1100), "A stable source clears burst history");
        Check(guard.Lost(20000) && !guard.Unstable, "Old losses expire");
        int lost = unchecked((int)0x887A0026);
        Check(new SharpGen.Runtime.SharpGenException(new SharpGen.Runtime.Result(lost)).HResult == lost, "SharpGen error preserves native HRESULT");
        double now = 0; int opened = 0, frames = 0, disposed = 0; bool running = true;
        var pins = new List<long?>(); var names = new List<string>(); var phases = new List<string>();
        await DesktopDuplicationCapture.RunAsync("chosen-monitor", 60, 1920, 1080, 88, () => running, () => true,
            _ => { frames++; if (frames == 2) running = false; }, phases.Add, _ => {}, (display, pin) =>
            {
                names.Add(display); pins.Add(pin); opened++;
                if (opened == 2) throw new COMException("mode switch", lost);
                int calls = 0;
                return new FakeSource(7, (ready, publish) =>
                {
                    if (++calls > 1) throw new COMException("access lost", lost);
                    if (ready()) publish(new byte[] { 1 });
                }, () => disposed++);
            }, () => { now += 500; return Task.CompletedTask; }, () => now);
        Check(frames == 2 && disposed == 2, "Lost source is disposed and actual frames resume");
        Check(names.All(name => name == "chosen-monitor") && pins.SequenceEqual(new long?[] { null, 7, 7 }), "Same monitor and adapter retained across recreation");
        Check(phases.Count(phase => phase == "ready") == 2 && phases.Contains("recovering"), "Recovery phases follow actual images");

        now = 0; opened = 0;
        try
        {
            await DesktopDuplicationCapture.RunAsync("gone", 60, 0, 0, 88, () => true, () => true, _ => throw new Exception("No frame expected"), _ => {}, _ => {},
                (_, _) => { opened++; throw new COMException("unavailable", lost); }, () => { now += 500; return Task.CompletedTask; }, () => now);
            throw new Exception("Unbounded retries");
        }
        catch (InvalidOperationException) { Check(now == 15000 && opened == 31, "Disconnected screen retries are bounded"); }

        opened = 0;
        try
        {
            await DesktopDuplicationCapture.RunAsync("chosen", 60, 0, 0, 88, () => true, () => true, _ => {}, _ => {}, _ => {},
                (_, _) => { opened++; throw new COMException("invalid", unchecked((int)0x80070057)); });
            throw new Exception("Expected API failure");
        }
        catch (COMException) { Check(opened == 1, "Invalid arguments do not retry"); }
        now = 0; disposed = 0;
        try
        {
            await DesktopDuplicationCapture.RunAsync("silent-reopen", 60, 0, 0, 88, () => true, () => true,
                _ => throw new Exception("No image expected"), _ => {}, _ => {},
                (_, _) => new FakeSource(7, (_, _) => now += 100, () => disposed++), clock: () => now);
            throw new Exception("A reopened source must produce its initial frame");
        }
        catch (InvalidOperationException) { Check(now == 15000 && disposed == 1, "Successful open without actual frames still expires and releases resources"); }
        now = 0; opened = 0; disposed = 0;
        try
        {
            await DesktopDuplicationCapture.RunAsync("reused-output-name", 60, 0, 0, 88, () => true, () => true,
                _ => throw new Exception("Changed monitor must not publish"), _ => {}, _ => {},
                (_, _) => new FakeSource(7, (_, _) => throw new COMException("mode switch", lost), () => disposed++, ++opened == 1 ? "monitor-a" : "monitor-b"),
                () => { now += 500; return Task.CompletedTask; }, () => now);
            throw new Exception("Different monitor must fail closed");
        }
        catch (InvalidOperationException) { Check(opened == 2 && disposed == 2, "Monitor identity change never captures the replacement"); }
        Console.WriteLine("PASS: DXGI recovery preserves monitor/adapter, releases sources, resumes frames, bounds retries and propagates fatal errors; no screen captured");
    }
    private sealed class FakeSource(long adapter, Action<Func<bool>, Action<byte[]>> next, Action dispose, string identity = "physical-monitor") : DesktopDuplicationCapture.ISource
    {
        public long AdapterId => adapter;
        public string MonitorIdentity => identity;
        public void Next(Func<bool> shouldCapture, Action<byte[]> publish) => next(shouldCapture, publish);
        public void Dispose() => dispose();
    }
}
