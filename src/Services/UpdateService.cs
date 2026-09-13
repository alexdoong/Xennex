using Xennex.Models;
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

        public UpdateService()
        {
            _httpClient = new HttpClient();
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
                var response = await _httpClient.GetAsync(apiUrl);

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

                if (root.TryGetProperty("assets", out var assetsProp) && assetsProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var asset in assetsProp.EnumerateArray())
                    {
                        string name = asset.TryGetProperty("name", out var aName) ? aName.GetString() ?? "" : "";
                        if (name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase) ||
                            name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ||
                            name.EndsWith(".msi", StringComparison.OrdinalIgnoreCase))
                        {
                            if (asset.TryGetProperty("browser_download_url", out var dUrl))
                            {
                                result.DownloadUrl = dUrl.GetString() ?? "";
                            }
                            if (asset.TryGetProperty("size", out var aSize))
                            {
                                result.AssetSize = aSize.GetInt64();
                            }
                            break;
                        }
                    }
                }

                result.HasUpdate = IsVersionNewer(CurrentVersion, tagName);
                if (result.HasUpdate && string.IsNullOrEmpty(result.DownloadUrl))
                {
                    result.ErrorMessage = $"Nova versão {tagName} encontrada, mas o arquivo de instalação ainda não foi anexado à release do GitHub.";
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
            if (string.IsNullOrWhiteSpace(downloadUrl))
                return false;

            try
            {
                string tempDir = Path.GetTempPath();
                string appDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                string exePath = Path.Combine(appDir, "Xennex.exe");

                string ext = Path.GetExtension(new Uri(downloadUrl).AbsolutePath);
                if (string.IsNullOrEmpty(ext)) ext = ".zip";

                string updatePackagePath = Path.Combine(tempDir, $"Xennex_Update_{Guid.NewGuid():N}{ext}");
                string updaterScriptPath = Path.Combine(tempDir, $"xennex_updater_{Guid.NewGuid():N}.ps1");

                // Download streaming direto para o disco para economizar RAM
                using (var response = await _httpClient.GetAsync(downloadUrl, HttpCompletionOption.ResponseHeadersRead))
                {
                    response.EnsureSuccessStatusCode();
                    using (var contentStream = await response.Content.ReadAsStreamAsync())
                    using (var fs = new FileStream(updatePackagePath, FileMode.Create, FileAccess.Write, FileShare.None, 81920, true))
                    {
                        await contentStream.CopyToAsync(fs);
                    }
                }

                int currentPid = Process.GetCurrentProcess().Id;

                // Script PowerShell seguro que aguarda o encerramento do processo e protege configs e skins
                string scriptContent;
                using (var resource = typeof(UpdateService).Assembly.GetManifestResourceStream("Xennex.InstallUpdate.ps1"))
                {
                    if (resource == null) throw new InvalidOperationException("Script de atualizacao ausente.");
                    using (var reader = new StreamReader(resource)) scriptContent = reader.ReadToEnd();
                }

                await File.WriteAllTextAsync(updaterScriptPath, scriptContent);

                var psi = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = $"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"{updaterScriptPath}\" -TargetPid {currentPid} -UpdateFile \"{updatePackagePath}\" -AppDir \"{appDir}\" -ExePath \"{exePath}\"",
                    CreateNoWindow = true,
                    UseShellExecute = false
                };
                Process.Start(psi);

                Application.Current.Dispatcher.Invoke(() =>
                {
                    Application.Current.Shutdown();
                });

                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[UpdateService] Erro ao aplicar atualizacao: {ex.Message}");
                return false;
            }
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

            return !string.Equals(c, l, StringComparison.OrdinalIgnoreCase);
        }
    }
}
