using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Net.WebSockets;
using Xennex.CaptureWorker;

internal static class GameWorkerTests
{
    [DllImport("user32.dll")] static extern bool PostMessage(nint window, uint message, nint w, nint l);
    internal static async Task Run(string worker, string directory)
    {
        worker = Path.GetFullPath(worker); directory = Path.GetFullPath(directory);
        string tampered = Path.Combine(Path.GetTempPath(), "Xennex-GameHook-" + Guid.NewGuid().ToString("N") + ".dll");
        try
        {
            File.Copy(Path.Combine(directory, "Xennex.GameHook64.dll"), tampered);
            using (var file = new FileStream(tampered, FileMode.Open, FileAccess.ReadWrite))
            { file.Position = 0x70; int value = file.ReadByte(); file.Position = 0x70; file.WriteByte((byte)(value ^ 1)); }
            try { NativeGameSession.VerifyBinary(tampered); throw new Exception("Tampered hook signature accepted"); }
            catch (Exception error) when (error is InvalidOperationException or System.Security.Cryptography.CryptographicException) { }
        }
        finally { File.Delete(tampered); }
        foreach (string bits in new[] { "32", "64" })
        {
            using var fixture = Process.Start(new ProcessStartInfo(Path.Combine(directory, $"Xennex.OpenGlFixture{bits}.exe"))
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true }) ?? throw new Exception("Own GL fixture missing");
            try
            {
                string line = await fixture.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(10)) ?? "";
                string[] values = line.Split(' ');
                if (values.Length != 2 || int.Parse(values[0]) != fixture.Id) throw new Exception("Own fixture identity invalid");
                long hwnd = long.Parse(values[1]);
                foreach (int target in new[] { 30, 60, 120 })
                {
                    int count = 0; long first = 0, last = 0; var hashes = new HashSet<string>();
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(4));
                    await WorkerStreamFixture.Run(worker, "", jpeg =>
                    {
                        long now = Stopwatch.GetTimestamp(); if (count == 0) first = now; last = now; count++;
                        hashes.Add(Convert.ToHexString(SHA256.HashData(jpeg)));
                        if (count % 15 != 1) return;
                        using var stream = new MemoryStream(jpeg); using var image = new Bitmap(stream);
                        Color top = image.GetPixel(10, 10), bottom = image.GetPixel(10, image.Height - 10);
                        if (top.B < 180 || top.R > 70 || bottom.R < 180 || bottom.B > 70) throw new Exception("Game Worker JPEG orientation/channels incorrect");
                    }, _ => { }, timeout.Token, target, "480p", backend: "game", hwnd: hwnd, gamePid: fixture.Id, gameStart: fixture.StartTime.ToUniversalTime().Ticks);
                    double fps = count < 2 ? 0 : (count - 1) * (double)Stopwatch.Frequency / (last - first);
                    Console.WriteLine($"GameWorker{bits}: target={target} socket={fps:F1} JPEGs={count} changing={hashes.Count}");
                    if (count < 10 || hashes.Count < 5 || fps < target * .6) throw new Exception("Game Worker throughput/content failed");
                    await Task.Delay(300); // Owner-exit cleanup in the injected module.
                    if (fixture.HasExited) throw new Exception("Game fixture crashed after Worker exit");
                }
                try
                {
                    using var conflict = await NativeGameSession.OpenAsync(fixture.Id, hwnd, fixture.StartTime.ToUniversalTime().Ticks, 60, directory);
                    throw new Exception("A second hook path must not be loaded over the existing module");
                }
                catch (InvalidOperationException error) when (error.Message.Contains("183")) { }
                bool reset = false;
                using (var limit = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
                {
                    try
                    {
                        await WorkerStreamFixture.Run(worker, "", _ => { if (!reset) { reset = true; PostMessage((nint)hwnd, 0x8001, 0, 0); } }, _ => {}, limit.Token,
                            60, "480p", backend: "game", hwnd: hwnd, gamePid: fixture.Id, gameStart: fixture.StartTime.ToUniversalTime().Ticks);
                        throw new Exception("Context recreation must stop capture instead of deleting objects in a reused context");
                    }
                    catch (WebSocketException) when (reset) { }
                    catch (Exception error) when (reset && error.Message == "Packaged capture closed before fixture completion") { }
                }
                await Task.Delay(1200);
                if (!reset || fixture.HasExited) throw new Exception("Own fixture did not survive context reset");
                try
                {
                    using var invalid = await NativeGameSession.OpenAsync(fixture.Id, hwnd, fixture.StartTime.ToUniversalTime().Ticks, 60, Path.Combine(Path.GetDirectoryName(worker)!, "GameCapture"));
                    throw new Exception("Unsafe GL context must require game restart");
                }
                catch (InvalidOperationException error) when (error.Message.Contains("5023")) { } // ERROR_INVALID_STATE
                PostMessage((nint)hwnd, 0x10, 0, 0); await fixture.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
                if (fixture.ExitCode != 0) throw new Exception("Own GL fixture failed state preservation");
            }
            finally { if (!fixture.HasExited) { fixture.Kill(); await fixture.WaitForExitAsync(); } }
        }
        Console.WriteLine("PASS game backend: own x86/x64 OpenGL -> IPC -> JPEG -> authenticated socket, repeated Worker termination.");
    }
}
