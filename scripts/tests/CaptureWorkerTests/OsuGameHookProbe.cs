using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography.X509Certificates;
using Microsoft.Win32.SafeHandles;

// Explicit opt-in only. Does not start OBS, change game settings or capture a monitor.
internal static class OsuGameHookProbe
{
    [DllImport("user32.dll")] static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(nint window, out uint pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern SafeProcessHandle OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool IsWow64Process(SafeProcessHandle process, out bool wow);

    static bool Foreground(int pid)
    { GetWindowThreadProcessId(GetForegroundWindow(), out uint current); return current == pid; }

    internal static void VerifyBinaries(string directory)
    {
        using var resource = typeof(OsuGameHookProbe).Assembly.GetManifestResourceStream("Xennex.PublisherThumbprint")
            ?? throw new InvalidOperationException("Publisher pin missing");
        using var reader = new StreamReader(resource);
        string expected = reader.ReadToEnd().Trim();
        foreach (string name in new[] { "Xennex.GameHook32.dll", "Xennex.GameHook64.dll", "Xennex.GameInjector32.exe", "Xennex.GameInjector64.exe" })
        {
            string file = Path.Combine(Path.GetFullPath(directory), name);
            using var certificate = new X509Certificate2(X509Certificate.CreateFromSignedFile(file));
            if (!certificate.Thumbprint.Equals(expected, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Unexpected publisher: " + name);
            uint result = Xennex.Build.AuthenticodeVerification.Check(file);
            if (result != 0 && result != 0x800B0109) throw new InvalidOperationException($"Invalid Authenticode integrity: {name} 0x{result:x8}");
        }
    }

    internal static async Task Run(string directory)
    {
        directory = Path.GetFullPath(directory);
        VerifyBinaries(directory); // Fail before opening the game for modification.
        using var game = Process.GetProcessesByName("osu!").SingleOrDefault() ?? throw new InvalidOperationException("Expected one running osu! process");
        Console.WriteLine("WAIT: osu! foreground/fullscreen, movement for about 15 seconds; own signed OpenGL hook, no images saved.");
        var deadline = Stopwatch.StartNew();
        while (!Foreground(game.Id))
        {
            if (game.HasExited || deadline.Elapsed > TimeSpan.FromSeconds(90)) throw new InvalidOperationException("No foreground osu!; no hook loaded.");
            await Task.Delay(100);
        }
        nint window = GetForegroundWindow();
        using var process = OpenProcess(0x1040, false, game.Id); // limited query + duplicate handles, no elevation.
        if (process.IsInvalid || !IsWow64Process(process, out bool wow)) throw new System.ComponentModel.Win32Exception();
        string bits = Environment.Is64BitOperatingSystem && !wow ? "64" : "32";
        foreach (int fps in new[] { 30, 60, 120 })
        {
            if (!Foreground(game.Id)) throw new OperationCanceledException("osu! left foreground before hook session");
            await GameHookTests.Session(directory, bits, game, process, window, fps, synthetic: false, foreground: () => Foreground(game.Id));
        }
        Console.WriteLine("PASS raw OpenGL game capture only; does not establish JPEG/WebRTC FPS received by friends.");
    }
}
