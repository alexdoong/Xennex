using Xennex.Models;
using System;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace Xennex.Services
{
    public class SkinService
    {
        private readonly ConfigService _configService;
        private readonly string _skinsDirectory;

        public SkinService(ConfigService configService)
        {
            _configService = configService;
            string exePath = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName;
            string baseDir = System.IO.Path.GetDirectoryName(exePath);
            _skinsDirectory = Path.Combine(baseDir, "wwwroot", "skins");

            if (!Directory.Exists(_skinsDirectory))
            {
                Directory.CreateDirectory(_skinsDirectory);
            }

            EnsureDefaultSkin();
        }

        private void EnsureDefaultSkin()
        {
            try
            {
                string defaultDir = Path.Combine(_skinsDirectory, "default");
                if (!Directory.Exists(defaultDir))
                {
                    Directory.CreateDirectory(defaultDir);
                }

                string jsonPath = Path.Combine(defaultDir, "skin.json");
                if (!File.Exists(jsonPath))
                {
                    var defaultSkin = new SkinConfig();
                    string json = JsonSerializer.Serialize(defaultSkin, new JsonSerializerOptions { WriteIndented = true });
                    File.WriteAllText(jsonPath, json);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SkinService] Falha ao inicializar skin padrao: {ex.Message}");
            }
        }

        public string[] GetAvailableSkins()
        {
            if (!Directory.Exists(_skinsDirectory)) return new string[] { "default" };

            var dirs = Directory.GetDirectories(_skinsDirectory);
            var skins = dirs.Select(d => new DirectoryInfo(d).Name).ToList();

            if (!skins.Contains("default"))
            {
                skins.Insert(0, "default");
            }

            return skins.ToArray();
        }

        public string GetActiveSkinConfig()
        {
            string skinName = _configService.Config.ActiveSkin;
            if (string.IsNullOrEmpty(skinName)) skinName = "default";
            return GetSkinConfig(skinName);
        }

        public string GetSkinConfig(string skinName)
        {
            if (string.IsNullOrEmpty(skinName)) skinName = "default";

            string skinJsonPath = Path.Combine(_skinsDirectory, skinName, "skin.json");
            if (File.Exists(skinJsonPath))
            {
                try
                {
                    return File.ReadAllText(skinJsonPath);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[SkinService] Erro ao ler skin.json de {skinName}: {ex.Message}");
                }
            }

            var fallback = new SkinConfig { Name = skinName };
            return JsonSerializer.Serialize(fallback, new JsonSerializerOptions { WriteIndented = true });
        }

        public bool SaveSkinConfig(string skinName, string json)
        {
            if (string.IsNullOrEmpty(skinName)) skinName = _configService.Config.ActiveSkin ?? "default";

            try
            {
                string targetDir = Path.Combine(_skinsDirectory, skinName);
                if (!Directory.Exists(targetDir))
                {
                    Directory.CreateDirectory(targetDir);
                }

                string skinJsonPath = Path.Combine(targetDir, "skin.json");
                File.WriteAllText(skinJsonPath, json);
                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SkinService] Erro ao salvar skin.json para {skinName}: {ex.Message}");
                return false;
            }
        }

        public bool CreateNewSkin(string newSkinName, string baseSkinName)
        {
            if (string.IsNullOrWhiteSpace(newSkinName)) return false;

            string cleanName = string.Concat(newSkinName.Split(Path.GetInvalidFileNameChars())).Trim();
            if (string.IsNullOrEmpty(cleanName)) return false;

            try
            {
                string targetDir = Path.Combine(_skinsDirectory, cleanName);
                if (!Directory.Exists(targetDir))
                {
                    Directory.CreateDirectory(targetDir);
                }

                string baseConfigJson = GetSkinConfig(baseSkinName);
                SkinConfig config;
                try
                {
                    config = JsonSerializer.Deserialize<SkinConfig>(baseConfigJson) ?? new SkinConfig();
                }
                catch
                {
                    config = new SkinConfig();
                }

                config.Name = cleanName;
                string newJson = JsonSerializer.Serialize(config, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(Path.Combine(targetDir, "skin.json"), newJson);

                _configService.Config.ActiveSkin = cleanName;
                _configService.SaveConfig();
                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SkinService] Erro ao criar nova skin {newSkinName}: {ex.Message}");
                return false;
            }
        }

        public string PickAndImportAsset(string skinName, string assetType)
        {
            if (string.IsNullOrEmpty(skinName)) skinName = _configService.Config.ActiveSkin ?? "default";
            string selectedFilePath = null;

            try
            {
                var app = System.Windows.Application.Current;
                if (app != null)
                {
                    app.Dispatcher.Invoke(() =>
                    {
                        var dlg = new Microsoft.Win32.OpenFileDialog();
                        if (assetType == "video")
                        {
                            dlg.Filter = "Arquivos de Vídeo (*.mp4;*.webm;*.mov)|*.mp4;*.webm;*.mov|Todos os Arquivos (*.*)|*.*";
                        }
                        else if (assetType == "image")
                        {
                            dlg.Filter = "Arquivos de Imagem (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)|*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp|Todos os Arquivos (*.*)|*.*";
                        }
                        else
                        {
                            dlg.Filter = "Arquivos de Mídia (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.mp4;*.webm)|*.png;*.jpg;*.jpeg;*.webp;*.gif;*.mp4;*.webm|Todos os Arquivos (*.*)|*.*";
                        }

                        if (dlg.ShowDialog() == true)
                        {
                            selectedFilePath = dlg.FileName;
                        }
                    });
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SkinService] Erro ao abrir diálogo de arquivo: {ex.Message}");
                return "";
            }

            if (string.IsNullOrEmpty(selectedFilePath) || !File.Exists(selectedFilePath))
            {
                return "";
            }

            try
            {
                string assetsDir = Path.Combine(_skinsDirectory, skinName, "assets");
                if (!Directory.Exists(assetsDir))
                {
                    Directory.CreateDirectory(assetsDir);
                }

                string ext = Path.GetExtension(selectedFilePath);
                string rawName = Path.GetFileNameWithoutExtension(selectedFilePath);
                string cleanRawName = string.Concat(rawName.Split(Path.GetInvalidFileNameChars()));
                string fileName = $"{assetType}_{DateTime.Now:yyyyMMdd_HHmmss}_{cleanRawName}{ext}";
                string destPath = Path.Combine(assetsDir, fileName);

                File.Copy(selectedFilePath, destPath, true);

                return $"https://appassets/skins/{skinName}/assets/{fileName}";
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SkinService] Erro ao importar asset: {ex.Message}");
                return "";
            }
        }

        public void OpenSkinFolder()
        {
            string skinName = _configService.Config.ActiveSkin;
            if (string.IsNullOrEmpty(skinName)) skinName = "default";

            string targetDir = Path.Combine(_skinsDirectory, skinName);
            if (!Directory.Exists(targetDir))
            {
                Directory.CreateDirectory(targetDir);
            }

            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo()
                {
                    FileName = targetDir,
                    UseShellExecute = true,
                    Verb = "open"
                });
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SkinService] Erro ao abrir pasta da skin: {ex.Message}");
            }
        }
    }
}

