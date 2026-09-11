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
        public string CurrentVersion { get; set; } = "v0.2.2";
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
        public const string CurrentVersion = "v0.2.2";
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
                string updaterScriptPath = Path.Combine(tempDir, "xennex_updater.ps1");

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
                string scriptContent = @"param(
    [int]$TargetPid,
    [string]$UpdateFile,
    [string]$AppDir,
    [string]$ExePath
)

$ErrorActionPreference = 'Continue'

# 1. Aguardar o encerramento suave do Xennex
if ($TargetPid -gt 0) {
    try {
        Wait-Process -Id $TargetPid -Timeout 15 -ErrorAction SilentlyContinue
    } catch {}
}
Start-Sleep -Seconds 1

# 2. Garantir que nao haja processos filhos residuais bloqueando os arquivos
$attempts = 0
while ((Get-Process Xennex -ErrorAction SilentlyContinue) -and $attempts -lt 10) {
    Start-Sleep -Milliseconds 500
    $attempts++
}

if ($UpdateFile.EndsWith('.zip', [System.StringComparison]::OrdinalIgnoreCase)) {
    $extractDir = Join-Path $env:TEMP ('Xennex_Extract_' + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

    try {
        Expand-Archive -Path $UpdateFile -DestinationPath $extractDir -Force

        # Se o zip tiver uma subpasta unica (ex: Xennex-v0.2.2-win64), detectar
        $items = Get-ChildItem -Path $extractDir
        $sourceDir = $extractDir
        if ($items.Count -eq 1 -and $items[0].PSIsContainer -and (Test-Path (Join-Path $items[0].FullName 'Xennex.exe'))) {
            $sourceDir = $items[0].FullName
        }

        # Copiar arquivos atualizando o app, mas preservando Data/config.txt e skins customizadas do usuario
        Get-ChildItem -Path $sourceDir | ForEach-Object {
            $dest = Join-Path $AppDir $_.Name
            if ($_.PSIsContainer -and $_.Name -eq 'Data') {
                New-Item -ItemType Directory -Path $dest -Force | Out-Null
                Get-ChildItem -Path $_.FullName | ForEach-Object {
                    $fileDest = Join-Path $dest $_.Name
                    if (-not (Test-Path $fileDest)) {
                        Copy-Item $_.FullName $fileDest -Force
                    }
                }
            } elseif ($_.PSIsContainer -and $_.Name -eq 'wwwroot') {
                New-Item -ItemType Directory -Path $dest -Force | Out-Null
                Copy-Item -Recurse -Path (Join-Path $_.FullName '*') -Destination $dest -Force
            } else {
                Copy-Item -Recurse -Path $_.FullName -Destination $dest -Force
            }
        }
    }
    catch {
        Set-Content -Path (Join-Path $env:TEMP 'xennex_update_error.log') -Value $_.Exception.ToString()
    }
    finally {
        Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
        Remove-Item -Force $UpdateFile -ErrorAction SilentlyContinue
    }

    Start-Process -FilePath $ExePath
} elseif ($UpdateFile.EndsWith('.exe', [System.StringComparison]::OrdinalIgnoreCase)) {
    Start-Process -FilePath $UpdateFile
}
";

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
