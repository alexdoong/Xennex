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
    public class UpdateCheckResult
    {
        public bool Success { get; set; }
        public bool HasUpdate { get; set; }
        public string CurrentVersion { get; set; } = "v0.2.0";
        public string LatestVersion { get; set; } = "";
        public string ReleaseTitle { get; set; } = "";
        public string ReleaseNotes { get; set; } = "";
        public string HtmlUrl { get; set; } = "";
        public string DownloadUrl { get; set; } = "";
        public long AssetSize { get; set; }
        public string ErrorMessage { get; set; } = "";
    }

    public class UpdateService
    {
        public const string CurrentVersion = "v0.2.0";
        private const string RepoOwner = "alexdoong";
        private const string RepoName = "Xennex";
        private readonly HttpClient _httpClient;

        public UpdateService()
        {
            _httpClient = new HttpClient();
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "Xennex-App/" + CurrentVersion);
            _httpClient.Timeout = TimeSpan.FromSeconds(15);
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
                    result.ErrorMessage = $"GitHub API retornou codigo: {(int)response.StatusCode}";
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
                        if (name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
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
                result.Success = true;
            }
            catch (HttpRequestException ex)
            {
                result.Success = false;
                result.ErrorMessage = "Sem conexao ao verificar atualizacoes: " + ex.Message;
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
                string zipPath = Path.Combine(tempDir, "Xennex_Update.zip");
                string appDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                string exePath = Path.Combine(appDir, "Xennex.exe");
                string updaterScript = Path.Combine(tempDir, "xennex_updater.bat");

                byte[] zipBytes = await _httpClient.GetByteArrayAsync(downloadUrl);
                await File.WriteAllBytesAsync(zipPath, zipBytes);

                string scriptContent = "@echo off\r\n" +
                    "chcp 65001 >nul\r\n" +
                    "echo [Xennex Updater] Aguardando fechamento do aplicativo...\r\n" +
                    "timeout /t 2 /nobreak >nul\r\n" +
                    "echo [Xennex Updater] Instalando nova versao...\r\n" +
                    "powershell -NoProfile -Command \"Expand-Archive -Path '" + zipPath + "' -DestinationPath '" + appDir + "' -Force\"\r\n" +
                    "echo [Xennex Updater] Reiniciando Xennex...\r\n" +
                    "start \"\" \"" + exePath + "\"\r\n" +
                    "del \"" + zipPath + "\" >nul 2>&1\r\n";

                await File.WriteAllTextAsync(updaterScript, scriptContent);

                var psi = new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/c \"{updaterScript}\"",
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
