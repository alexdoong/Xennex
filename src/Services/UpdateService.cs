using Xennex.Models;
using Xennex.Services.Updates;
using System.Threading;
using System.Collections.Generic;
using System.Reflection;
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;

namespace Xennex.Services
{
    public class UpdateService
    {
        public static string CurrentVersion
        {
            get
            {
                try
                {
                    var asm = Assembly.GetExecutingAssembly();
                    var infoVer = asm.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
                    if (!string.IsNullOrWhiteSpace(infoVer))
                    {
                        int plusIdx = infoVer.IndexOf('+');
                        string ver = plusIdx >= 0 ? infoVer.Substring(0, plusIdx) : infoVer;
                        return ver.StartsWith("v", StringComparison.OrdinalIgnoreCase) ? ver : "v" + ver;
                    }
                    var v = asm.GetName().Version;
                    if (v != null)
                    {
                        return $"v{v.Major}.{v.Minor}.{v.Build}";
                    }
                }
                catch (Exception ex) { AppLog.Error("Version", ex); }
                return "unknown";
            }
        }
        private const string RepoOwner = "alexdoong";
        private const string RepoName = "Xennex";
        private readonly HttpClient _httpClient;
        private readonly SemaphoreSlim _updating = new(1, 1);

        public UpdateService()
        {
            _httpClient = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false });
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "Xennex-App/" + CurrentVersion);
            _httpClient.Timeout = TimeSpan.FromSeconds(30);
        }

        public async Task<UpdateCheckResult> CheckForUpdatesAsync()
        {
            var result = new UpdateCheckResult
            {
                CurrentVersion = CurrentVersion
            };

            try
            {
                string apiUrl = $"https://api.github.com/repos/{RepoOwner}/{RepoName}/releases/latest";
                using var response = await _httpClient.GetAsync(apiUrl);

                if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
                {
                    result.Success = true;
                    result.HasUpdate = false;
                    result.ErrorMessage = "Nenhuma release publicada no GitHub ainda.";
                    return result;
                }

                if (!response.IsSuccessStatusCode)
                {
                    result.Success = false;
                    result.ErrorMessage = $"GitHub API retornou código: {(int)response.StatusCode}";
                    return result;
                }

                string json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;

                string tagName = root.TryGetProperty("tag_name", out var tagProp) ? tagProp.GetString() ?? "" : "";
                string title = root.TryGetProperty("name", out var nameProp) ? nameProp.GetString() ?? "" : "";
                string body = root.TryGetProperty("body", out var bodyProp) ? bodyProp.GetString() ?? "" : "";
                string htmlUrl = root.TryGetProperty("html_url", out var urlProp) ? urlProp.GetString() ?? "" : "";

                result.LatestVersion = tagName;
                result.ReleaseTitle = string.IsNullOrWhiteSpace(title) ? tagName : title;
                result.ReleaseNotes = body;
                result.HtmlUrl = htmlUrl;

                result.HasUpdate = IsVersionNewer(CurrentVersion, tagName);
                if (result.HasUpdate)
                {
                    try
                    {
                        var asset = UpdatePolicy.ReadApprovedAsset(root, CurrentVersion);
                        result.DownloadUrl = asset.Url; result.AssetSize = asset.Size;
                    }
                    catch (Exception error) when (error is InvalidDataException || error is JsonException || error is InvalidOperationException || error is KeyNotFoundException)
                    { result.ErrorMessage = error.Message; }
                }

                result.Success = true;
            }
            catch (HttpRequestException ex)
            {
                result.Success = false;
                result.ErrorMessage = "Sem conexão ao verificar atualizações: " + ex.Message;
            }
            catch (Exception ex)
            {
                result.Success = false;
                result.ErrorMessage = "Erro: " + ex.Message;
            }

            return result;
        }

        public async Task<bool> StartAutoUpdateAsync(string downloadUrl)
        {
            if (!UpdatePolicy.IsReleaseUrl(downloadUrl) || !await _updating.WaitAsync(0)) return false;
            string package = null, script = null, ready = null;
            Process updater = null;
            bool launched = false;
            try
            {
                using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(5));
                // Re-fetch trusted metadata: a frontend URL is never download authorization.
                using var metadata = await _httpClient.GetAsync(UpdatePolicy.LatestReleaseUrl, timeout.Token);
                metadata.EnsureSuccessStatusCode();
                using var document = JsonDocument.Parse(await metadata.Content.ReadAsStringAsync(timeout.Token));
                var asset = UpdatePolicy.ReadApprovedAsset(document.RootElement, CurrentVersion);
                if (downloadUrl != asset.Url) throw new InvalidDataException("A URL não corresponde ao pacote da release atual.");

                package = Path.Combine(Path.GetTempPath(), $"Xennex_Update_{Guid.NewGuid():N}.zip");
                script = Path.Combine(Path.GetTempPath(), $"xennex_updater_{Guid.NewGuid():N}.ps1");
                ready = Path.Combine(Path.GetTempPath(), $"xennex_update_ready_{Guid.NewGuid():N}.tmp");
                using (var response = await DownloadResponse(asset.Url, timeout.Token))
                {
                    using var input = await response.Content.ReadAsStreamAsync(timeout.Token);
                    using var output = new FileStream(package, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, true);
                    await UpdatePolicy.DownloadVerified(input, output, asset, timeout.Token);
                }
                string content = ReadResource("Xennex.InstallUpdate.ps1");
                string verifier = ReadResource("Xennex.AuthenticodeVerification.cs");
                content = content.Replace("# XENNEX_AUTHENTICODE_TYPE", "Add-Type -TypeDefinition @'\n" + verifier + "\n'@");
                await File.WriteAllTextAsync(script, content, timeout.Token);
                string appDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
                var psi = new ProcessStartInfo { FileName = "powershell.exe", CreateNoWindow = true, UseShellExecute = false };
                foreach (string argument in new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script,
                    "-TargetPid", Environment.ProcessId.ToString(), "-UpdateFile", package, "-AppDir", appDir,
                    "-ExePath", Path.Combine(appDir, "Xennex.exe"), "-ExpectedSha256", asset.Sha256,
                    "-ExpectedRoot", Path.GetFileNameWithoutExtension(asset.Name),
                    "-ExpectedPublisher", ReadResource("Xennex.PublisherThumbprint").Trim(), "-ReadyFile", ready })
                    psi.ArgumentList.Add(argument);
                updater = Process.Start(psi) ?? throw new IOException("O atualizador não iniciou.");
                var validationDeadline = DateTime.UtcNow.AddSeconds(60);
                while (!File.Exists(ready))
                {
                    if (updater.HasExited) throw new InvalidDataException("O pacote foi recusado pelo instalador. Consulte xennex_update_error.log na pasta temporária.");
                    if (DateTime.UtcNow >= validationDeadline) throw new TimeoutException("A validação da atualização não respondeu.");
                    await Task.Delay(100, timeout.Token);
                }
                if (await File.ReadAllTextAsync(ready, timeout.Token) != "verified")
                    throw new InvalidDataException("Confirmação de atualização inválida.");
                launched = true;
                Application.Current.Dispatcher.Invoke(() => Application.Current.Shutdown());
                return true;
            }
            catch (Exception error) { AppLog.Error("UpdateService", error); return false; }
            finally
            {
                if (!launched && updater != null)
                    try { if (!updater.HasExited) updater.Kill(entireProcessTree: true); }
                    catch (Exception error) { AppLog.Error("UpdateCleanup", error); }
                updater?.Dispose();
                if (ready != null) try { File.Delete(ready); } catch (Exception error) { AppLog.Error("UpdateCleanup", error); }
                if (!launched)
                    foreach (string path in new[] { package, script })
                        if (path != null) try { File.Delete(path); } catch (Exception error) { AppLog.Error("UpdateCleanup", error); }
                _updating.Release();
            }
        }

        private async Task<HttpResponseMessage> DownloadResponse(string address, CancellationToken token)
        {
            var uri = new Uri(address);
            for (int redirects = 0; redirects <= 5; redirects++)
            {
                if (!UpdatePolicy.IsDownloadRedirect(uri)) throw new InvalidDataException("Redirecionamento de atualização não autorizado.");
                var response = await _httpClient.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, token);
                if ((int)response.StatusCode is >= 300 and < 400)
                {
                    var location = response.Headers.Location;
                    response.Dispose();
                    if (location == null) throw new InvalidDataException("Redirecionamento sem endereço.");
                    uri = new Uri(uri, location); continue;
                }
                if (response.IsSuccessStatusCode) return response;
                response.Dispose(); throw new HttpRequestException("Falha ao baixar pacote da release.");
            }
            throw new InvalidDataException("Redirecionamentos demais no download.");
        }
        private static string ReadResource(string name)
        {
            using var stream = typeof(UpdateService).Assembly.GetManifestResourceStream(name)
                ?? throw new InvalidOperationException("Recurso de atualização ausente: " + name);
            using var reader = new StreamReader(stream); return reader.ReadToEnd();
        }

        private static bool IsVersionNewer(string currentVer, string latestVer)
        {
            if (string.IsNullOrWhiteSpace(latestVer)) return false;

            string c = currentVer.TrimStart('v', 'V').Trim();
            string l = latestVer.TrimStart('v', 'V').Trim();

            if (Version.TryParse(c, out var vCurrent) && Version.TryParse(l, out var vLatest))
            {
                return vLatest > vCurrent;
            }

            return false;
        }
    }
}
