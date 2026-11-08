using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

// Opt-in real-game probe. Records only aggregate counts/times, never pixels or game titles.
internal static class OsuCaptureProbe
{
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    private static bool IsGame(int pid)
    { GetWindowThreadProcessId(GetForegroundWindow(), out uint current); return current == pid; }
    internal static async Task Run(string executable, bool wgc = false)
    {
        using var game = Process.GetProcessesByName("osu!").SingleOrDefault() ?? throw new InvalidOperationException("Esperado um único processo osu! aberto.");
        Console.WriteLine("WAIT: coloque o osu! em primeiro plano e mantenha uma cena com movimento por cerca de 30 segundos.");
        var wait = Stopwatch.StartNew();
        while (!IsGame(game.Id))
        {
            if (game.HasExited || wait.ElapsedMilliseconds > 90000) throw new InvalidOperationException("O osu! não ficou em primeiro plano a tempo; nenhuma captura iniciada.");
            await Task.Delay(100);
        }
        string display = Screen.FromHandle(GetForegroundWindow()).DeviceName;
        long hwnd = GetForegroundWindow().ToInt64();
        foreach (int fps in wgc ? new[] { 60 } : new[] { 30, 60, 120 })
        {
            if (!IsGame(game.Id)) throw new InvalidOperationException("Teste interrompido: osu! saiu do primeiro plano.");
            int frames = 0, changes = 0, recovering = 0;
            long first = 0, last = 0; double maxGap = 0;
            byte[]? previous = null; JsonElement? metrics = null;
            bool focusLost = false;
            using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(9));
            var watch = Task.Run(async () =>
            {
                while (!stop.IsCancellationRequested)
                {
                    if (!IsGame(game.Id) || Screen.FromHandle(GetForegroundWindow()).DeviceName != display)
                    { focusLost = true; stop.Cancel(); break; }
                    await Task.Delay(25);
                }
            });
            Console.WriteLine($"MEASURE: osu! {(wgc ? "WGC janela" : "DXGI monitor")} 1080p, alvo {fps} FPS; imagens não são salvas.");
            try
            {
                await WorkerStreamFixture.Run(executable, display, bytes =>
                {
                    if (!IsGame(game.Id)) { focusLost = true; stop.Cancel(); return; }
                    long now = Stopwatch.GetTimestamp();
                    if (frames == 0) first = now;
                    else maxGap = Math.Max(maxGap, (now - last) * 1000.0 / Stopwatch.Frequency);
                    last = now; frames++;
                    var hash = SHA256.HashData(bytes);
                    if (previous == null || !hash.SequenceEqual(previous)) changes++;
                    previous = hash;
                }, phase => { if (phase == "recovering") recovering++; }, stop.Token, fps, "1080p", value => metrics = value.Clone(), wgc ? "wgc" : "dxgi", wgc ? hwnd : 0);
            }
            finally { stop.Cancel(); await watch; }
            if (focusLost) throw new InvalidOperationException("Teste pausado: o osu! saiu do primeiro plano ou mudou de monitor; worker encerrado.");
            if (frames < 2) throw new InvalidOperationException("A captura do osu! não produziu imagens suficientes.");
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                game = "osu!", backend = wgc ? "wgc-window" : "dxgi-monitor", targetFps = fps, resolution = "1080p", frames, distinctJpegs = changes,
                measuredFps = (frames - 1) * (double)Stopwatch.Frequency / (last - first), maxGapMs = maxGap,
                recoveryEvents = recovering, worker = metrics,
                note = "Contagem até o socket local; não mede FPS no amigo ou prova modo exclusivo. Preto de carregamento pode ser legítimo.",
            }));
            if (recovering >= 3) throw new InvalidOperationException("Captura instável: reinicializações repetidas no jogo real; não considerar a medição aprovada.");
        }
        Console.WriteLine("PASS: real osu! capture completed, aggregate measurements only; no frames saved.");
    }
}
