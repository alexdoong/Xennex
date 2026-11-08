using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Services;
using Xennex.Services.Security;
using Xennex.Services.Updates;

int passed = 0;
void Check(bool condition, string name) { if (!condition) throw new Exception(name); passed++; Console.WriteLine("PASS " + name); }
void Reject(Action action, string name) { try { action(); } catch { Check(true, name); return; } throw new Exception(name); }
async Task RejectAsync(Func<Task> action, string name) { try { await action(); } catch { Check(true, name); return; } throw new Exception(name); }
string directory = Path.Combine(Path.GetTempPath(), "Xennex-Security-" + Guid.NewGuid().ToString("N"));
string web = Path.Combine(directory, "wwwroot");
Directory.CreateDirectory(web);
var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start();
int port = ((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
var server = new LocalWebServer(web, port);
try
{
    File.WriteAllText(Path.Combine(web, "watch.html"), "PUBLIC_FIXTURE");
    string secret = Path.Combine(directory, "private.txt"); File.WriteAllText(secret, "PRIVATE_FIXTURE");
    if (OperatingSystem.IsWindows())
    {
        string oldRequestPath = new Uri("http://localhost/" + secret.Replace('\\', '/')).AbsolutePath.TrimStart('/');
        string legacy = Path.Combine(web, oldRequestPath.Replace('/', Path.DirectorySeparatorChar));
        Check(File.ReadAllText(legacy) == "PRIVATE_FIXTURE", "legacy drive-rooted URL reproduces read outside wwwroot");
    }
    foreach (string path in new[] { "/../private.txt", "/%2e%2e%2fprivate.txt", "/..%5cprivate.txt", "/%252e%252e%252fprivate.txt",
        "/C:/private.txt", "//server/share/file", "/file:stream", "/.. /private.txt" })
        Check(LocalRequestPolicy.ResolvePublicFile(web, path) == null, "reject path " + path);
    Check(LocalRequestPolicy.ResolvePublicFile(web, "/") == Path.Combine(web, "watch.html"), "normal static path");
    Check(LocalRequestPolicy.IsAppDocument("https://appassets/index.html?mode=viewer"), "trusted viewer document");
    foreach (string address in new[] { "http://appassets/index.html", "https://appassets.evil.test/index.html",
        "https://appassets/skins/custom/evil.html", "https://evil.test/index.html", "file:///index.html" })
        Check(!LocalRequestPolicy.IsAppDocument(address), "reject privileged document " + address);
    string token = LocalRequestPolicy.CaptureToken;
    Check(LocalRequestPolicy.IsCaptureAllowed("https://appassets", token, token), "trusted capture authorization");
    Check(!LocalRequestPolicy.IsCaptureAllowed("https://evil.test", token, token), "wrong capture origin");
    Check(!LocalRequestPolicy.IsCaptureAllowed("https://appassets", "a", token), "wrong capture token");
    server.Start();
    using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
    Check(await http.GetStringAsync($"http://127.0.0.1:{port}/") == "PUBLIC_FIXTURE", "real HTTP serves public frontend");
    using var foreign = new HttpRequestMessage(HttpMethod.Get, $"http://127.0.0.1:{port}/watch.html");
    foreign.Headers.Add("Origin", "https://evil.test");
    using var blocked = await http.SendAsync(foreign);
    Check(blocked.StatusCode == HttpStatusCode.Forbidden && !blocked.Headers.Contains("Access-Control-Allow-Origin"), "real HTTP rejects foreign origin without wildcard CORS");
    foreach (string target in new[] { "/%2e%2e%2fprivate.txt", "/" + secret.Replace('\\', '/') })
    {
        using var socket = new TcpClient(); await socket.ConnectAsync(IPAddress.Loopback, port);
        var bytes = Encoding.ASCII.GetBytes($"GET {target} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
        await socket.GetStream().WriteAsync(bytes);
        using var reader = new StreamReader(socket.GetStream());
        string reply = await reader.ReadToEndAsync().WaitAsync(TimeSpan.FromSeconds(5));
        Check(!reply.Contains("PRIVATE_FIXTURE") && !reply.StartsWith("HTTP/1.1 200"), "real raw HTTP blocks " + target);
    }
    foreach (var attack in new[] { ("https://evil.test", token), ("https://appassets", "wrong"), ("null", token) })
    {
        using var socket = new ClientWebSocket(); socket.Options.SetRequestHeader("Origin", attack.Item1);
        using var deadline = new CancellationTokenSource(3000);
        await RejectAsync(() => socket.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/audiostream?token={attack.Item2}"), deadline.Token), "real WS rejects unauthorized capture");
    }
    using (var socket = new ClientWebSocket())
    {
        socket.Options.SetRequestHeader("Origin", "https://appassets");
        using var deadline = new CancellationTokenSource(3000);
        await socket.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/audiostream?token={token}"), deadline.Token);
        byte[] buffer = new byte[512]; var message = await socket.ReceiveAsync(buffer, deadline.Token);
        Check(Encoding.UTF8.GetString(buffer, 0, message.Count).Contains("sampleRate"), "authorized audio WebSocket preserves format handshake");
        await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "test done", deadline.Token);
    }
    byte[] payload = Encoding.UTF8.GetBytes("synthetic release"); string hash = Convert.ToHexString(SHA256.HashData(payload));
    string url = "https://github.com/alexdoong/Xennex/releases/download/v0.2.4/Xennex-v0.2.4-win64.zip";
    JsonElement Release(string address, string digest, string tag = "v0.2.4") => JsonSerializer.SerializeToElement(new {
        draft = false, prerelease = false, tag_name = tag, assets = new[] { new { name = "Xennex-" + tag + "-win64.zip",
            browser_download_url = address, digest, size = payload.Length } } });
    var approved = UpdatePolicy.ReadApprovedAsset(Release(url, "sha256:" + hash), "v0.2.3");
    foreach (string address in new[] { "https://evil.test/release.zip", url.Replace("github.com", "github.com.evil.test"),
        url.Replace("https:", "http:"), url.Replace("/alexdoong/", "/other/"), url + "?x=1", url.Replace(".zip", ".exe") })
        Check(!UpdatePolicy.IsReleaseUrl(address), "reject update source " + address);
    Reject(() => UpdatePolicy.ReadApprovedAsset(Release(url, ""), "v0.2.3"), "missing digest fails closed");
    Reject(() => UpdatePolicy.ReadApprovedAsset(Release(url, "sha256:" + hash), "v0.2.4"), "no downgrade or same-version install");
    Check(!UpdatePolicy.IsDownloadRedirect(new Uri("https://release-assets.githubusercontent.com.evil.test/x")), "redirect suffix spoof rejected");
    await UpdatePolicy.DownloadVerified(new MemoryStream(payload), new MemoryStream(), approved, CancellationToken.None);
    Check(true, "verified download accepts matching size/hash");
    await RejectAsync(() => UpdatePolicy.DownloadVerified(new MemoryStream(Encoding.UTF8.GetBytes("tampered release!")), new MemoryStream(), approved, CancellationToken.None), "tampered download rejected");
    await RejectAsync(() => UpdatePolicy.DownloadVerified(new MemoryStream(payload), new MemoryStream(), approved with { Sha256 = new string('0', 64) }, CancellationToken.None), "wrong hash rejected at same size");
    Console.WriteLine($"Security checks: {passed} passed");
}
finally
{
    server.Stop();
    string temporaryRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    if (!Path.GetFullPath(directory).StartsWith(temporaryRoot + "Xennex-Security-", StringComparison.OrdinalIgnoreCase))
        throw new Exception("Unsafe fixture cleanup");
    Directory.Delete(directory, true);
}
