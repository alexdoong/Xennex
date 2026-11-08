using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text.Json;

internal static class WorkerStreamFixture
{
    internal static async Task Run(string executable, string display, Action<byte[]> inspect, Action<string> status, CancellationToken token,
        int fps = 30, string resolution = "720p", Action<JsonElement>? measure = null, string backend = "dxgi", long hwnd = 0, int gamePid = 0, long gameStart = 0)
    {
        using var reservation = new TcpListener(IPAddress.Loopback, 0); reservation.Start();
        int port = ((IPEndPoint)reservation.LocalEndpoint).Port; reservation.Stop();
        string secret = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true };
        foreach (string argument in new[] { "--backend", backend, "--display", display, "--hwnd", hwnd.ToString(), "--fps", fps.ToString(), "--res", resolution,
            "--port", port.ToString(), "--quality", "80", "--parentpid", Environment.ProcessId.ToString(), "--token", secret }) start.ArgumentList.Add(argument);
        if (backend == "game") foreach (string argument in new[] { "--gamepid", gamePid.ToString(), "--gamestart", gameStart.ToString() }) start.ArgumentList.Add(argument);
        using var worker = Process.Start(start) ?? throw new Exception("Packaged worker did not start");
        ClientWebSocket? socket = null;
        try
        {
            var deadline = Stopwatch.StartNew();
            while (!token.IsCancellationRequested && deadline.ElapsedMilliseconds < 10000)
            {
                if (worker.HasExited) throw new Exception("Packaged worker exited during startup");
                var attempt = new ClientWebSocket(); attempt.Options.SetRequestHeader("Origin", "https://appassets");
                try
                {
                    await attempt.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/videostream/?token={secret}"), token);
                    socket = attempt; break;
                }
                catch (WebSocketException) { attempt.Dispose(); await Task.Delay(100, token); }
                catch { attempt.Dispose(); throw; }
            }
            if (socket == null) throw new Exception("Packaged worker socket did not start");
            var buffer = new byte[65536];
            while (!token.IsCancellationRequested)
            {
                using var message = new MemoryStream();
                WebSocketReceiveResult result;
                do
                {
                    result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), token);
                    if (result.MessageType == WebSocketMessageType.Close) throw new Exception("Packaged capture closed before fixture completion");
                    message.Write(buffer, 0, result.Count);
                    if (message.Length > 8 * 1024 * 1024) throw new Exception("Oversized fixture message");
                } while (!result.EndOfMessage);
                if (result.MessageType == WebSocketMessageType.Binary) inspect(message.ToArray());
                else
                {
                    using var state = JsonDocument.Parse(message.ToArray());
                    if (state.RootElement.GetProperty("type").GetString() == "capture-status") status(state.RootElement.GetProperty("phase").GetString() ?? "");
                    else if (state.RootElement.GetProperty("type").GetString() == "capture-metrics") measure?.Invoke(state.RootElement);
                }
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        finally
        {
            socket?.Dispose();
            if (!worker.HasExited) { worker.Kill(); worker.WaitForExit(3000); }
        }
    }
}
