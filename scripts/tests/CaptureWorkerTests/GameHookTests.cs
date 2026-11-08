using System.Diagnostics;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class GameHookTests
{
    const int HeaderSize = 128, Capacity = 32 * 1024 * 1024;
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern SafeProcessHandle OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool DuplicateHandle(nint source, nint handle, SafeProcessHandle target, out nint duplicate, uint access, bool inherit, uint options);
    [DllImport("kernel32.dll")] static extern nint GetCurrentProcess();
    [DllImport("user32.dll")] static extern bool PostMessage(nint window, uint message, nint w, nint l);

    public static async Task Run(string directory)
    {
        directory = Path.GetFullPath(directory);
        foreach (string bits in new[] { "32", "64" })
        {
            var start = new ProcessStartInfo(Path.Combine(directory, $"Xennex.OpenGlFixture{bits}.exe"))
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            using var fixture = Process.Start(start) ?? throw new InvalidOperationException("Fixture did not start");
            try
            {
                string line = await fixture.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(10)) ?? "";
                string[] values = line.Split(' ');
                if (values.Length != 2 || int.Parse(values[0]) != fixture.Id) throw new Exception("Invalid own fixture identity: " + line);
                nint window = (nint)long.Parse(values[1]);
                using var process = OpenProcess(0x40, false, fixture.Id); // PROCESS_DUP_HANDLE, own child only.
                if (process.IsInvalid) throw new System.ComponentModel.Win32Exception();
                for (int cycle = 0; cycle < 3; cycle++)
                {
                    int fps = new[] { 30, 60, 120 }[cycle];
                    await Session(directory, bits, fixture, process, window, fps);
                    PostMessage(window, 0x8000, 800 + cycle * 100, 600 + cycle * 50);
                }
                PostMessage(window, 0x10, 0, 0);
                await fixture.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
                if (fixture.ExitCode != 0) throw new Exception($"Fixture{bits} crashed: {fixture.ExitCode}");
            }
            finally
            {
                if (!fixture.HasExited) { fixture.Kill(); await fixture.WaitForExitAsync(); }
            }
        }
        Console.WriteLine("PASS OpenGL hook: own x86/x64 processes, colors, cadence and repeated stop/start; no game loaded.");
    }

    internal static async Task Session(string directory, string bits, Process fixture, SafeProcessHandle target, nint window, int fps,
        bool synthetic = true, Func<bool>? foreground = null)
    {
        using var mapping = MemoryMappedFile.CreateNew(null, HeaderSize + Capacity);
        using var view = mapping.CreateViewAccessor();
        using var mutex = new Mutex();
        using var stop = new EventWaitHandle(false, EventResetMode.ManualReset);
        view.Write(0, 0x31434758u); view.Write(4, 1u); view.Write(8, (uint)HeaderSize); view.Write(12, (uint)Capacity);
        nint mapHandle = Duplicate(mapping.SafeMemoryMappedFileHandle.DangerousGetHandle(), target);
        nint mutexHandle = Duplicate(mutex.SafeWaitHandle.DangerousGetHandle(), target);
        nint stopHandle = Duplicate(stop.SafeWaitHandle.DangerousGetHandle(), target);
        var start = new ProcessStartInfo(Path.Combine(directory, $"Xennex.GameInjector{bits}.exe"))
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (string value in new[] { fixture.Id.ToString(), Path.Combine(directory, $"Xennex.GameHook{bits}.dll"),
            Environment.ProcessId.ToString(), window.ToString(), mapHandle.ToString(), mutexHandle.ToString(), stopHandle.ToString(), fps.ToString() })
            start.ArgumentList.Add(value);
        using var helper = Process.Start(start) ?? throw new Exception("Injector did not start");
        try
        {
            await helper.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(25));
            if (helper.ExitCode != 0) throw new Exception($"Own fixture initialization failed ({bits}): {helper.ExitCode} {await helper.StandardError.ReadToEndAsync()}");
            long last = 0, firstId = 0, firstQpc = 0, lastQpc = 0; int frames = 0;
            var changed = new HashSet<ulong>();
            var watch = Stopwatch.StartNew();
            while (watch.Elapsed < TimeSpan.FromSeconds(3))
            {
                if (fixture.HasExited) throw new Exception($"Selected process{bits} exited unexpectedly: {fixture.ExitCode}");
                if (foreground != null && !foreground()) throw new OperationCanceledException("osu! left foreground; hook session stopped.");
                if (view.ReadInt32(16) == -1) throw new Exception("Hook error " + view.ReadInt32(20));
                if (mutex.WaitOne(0))
                {
                    try
                    {
                        long id = view.ReadInt64(40);
                        if (id != last)
                        {
                            last = id;
                            int width = view.ReadInt32(24), height = view.ReadInt32(28), stride = view.ReadInt32(32);
                            if (width < 2 || height < 2 || stride != width * 4 || (long)stride * height > Capacity || view.ReadInt32(36) != 1)
                                throw new Exception("Malformed frame geometry");
                            if (synthetic)
                            {
                                uint bottom = view.ReadUInt32(HeaderSize + stride * 10 + 40), top = view.ReadUInt32(HeaderSize + stride * (height - 10) + 40);
                                if ((bottom & 0xffffff) != 0xff0000 || (top & 0xffffff) != 0xff) throw new Exception($"Wrong BGRA/bottom-up colors: {bottom:x8}/{top:x8}");
                            }
                            // Only aggregate fingerprints; never save or print image pixels.
                            ulong hash = 0;
                            for (int x = 0; x < width; x += 7) hash = unchecked(hash * 31 + view.ReadUInt32(HeaderSize + stride * (height / 2) + x * 4));
                            changed.Add(hash);
                            long qpc = view.ReadInt64(48);
                            if (firstQpc == 0) { firstQpc = qpc; firstId = id; }
                            if (qpc <= lastQpc) throw new Exception("Capture timestamp regressed");
                            lastQpc = qpc; frames++;
                        }
                    }
                    finally { mutex.ReleaseMutex(); }
                }
                await Task.Delay(1);
            }
            double measured = frames < 2 ? 0 : (last - firstId) * (double)Stopwatch.Frequency / (lastQpc - firstQpc);
            Console.WriteLine($"{(synthetic ? "Own OpenGL" : "osu! OpenGL")}{bits}: target={fps} produced={measured:F1} latestSamples={frames} changing={changed.Count} skips={view.ReadInt64(56)}");
            if (frames < 10 || changed.Count < 5 || measured < fps * .65 || measured > fps * 1.1) throw new Exception("Capture cadence/content failed");
        }
        finally
        {
            stop.Set();
            var deadline = Stopwatch.StartNew();
            while (view.ReadInt32(16) != 3 && !fixture.HasExited && deadline.Elapsed < TimeSpan.FromSeconds(4)) await Task.Delay(10);
            if (!helper.HasExited) { helper.Kill(); await helper.WaitForExitAsync(); }
        }
        if (view.ReadInt32(16) != 3) throw new Exception("Hook did not stop cleanly");
        long stoppedFrame = view.ReadInt64(40);
        await Task.Delay(100);
        if (view.ReadInt64(40) != stoppedFrame || fixture.HasExited) throw new Exception("Rendering stopped or capture continued after stop");
        // XGC_STOPPED is written before handles close; give lifetime thread time to finish reset.
        await Task.Delay(100);
    }

    static nint Duplicate(nint handle, SafeProcessHandle target)
    {
        if (!DuplicateHandle(GetCurrentProcess(), handle, target, out var duplicate, 0, false, 2)) throw new System.ComponentModel.Win32Exception();
        return duplicate;
    }
}
