using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using Xennex.Models;

namespace Xennex.Services;

/// <summary>Skin files stay inside their own directory; writes replace a complete validated JSON.</summary>
public sealed class SkinRepository
{
    public static readonly JsonSerializerOptions Json = new() { PropertyNameCaseInsensitive = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true };
    private readonly string root;
    private readonly object sync = new();
    public SkinRepository(string directory) { root = Path.GetFullPath(directory); Directory.CreateDirectory(root); SafeDirectory(root); }
    private static void SafeDirectory(string directory)
    {
        if (Directory.Exists(directory) && (File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Pastas de skin não podem ser links.");
    }
    public string DirectoryFor(string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Length > 80 || name != name.Trim() || name.EndsWith('.') ||
            name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || name is "." or ".." ||
            Regex.IsMatch(name, @"^(con|prn|aux|nul|com[0-9]|lpt[0-9])($|\.)", RegexOptions.IgnoreCase))
            throw new ArgumentException("Use um nome de até 80 caracteres, sem barras ou caracteres reservados.");
        SafeDirectory(root);
        string result = Path.Combine(root, name); SafeDirectory(result); return result;
    }
    public string[] List() => Directory.GetDirectories(root).Where(p => (File.GetAttributes(p) & FileAttributes.ReparsePoint) == 0)
        .Where(p => File.Exists(Path.Combine(p, "skin.json"))).Select(Path.GetFileName).OrderBy(n => n == "default" ? "" : n).ToArray();
    public SkinConfig Read(string name)
    {
        string file = Path.Combine(DirectoryFor(name), "skin.json");
        if (!File.Exists(file)) throw new FileNotFoundException("Skin não encontrada.");
        if ((File.GetAttributes(file) & FileAttributes.ReparsePoint) != 0 || new FileInfo(file).Length > 131072)
            throw new InvalidDataException("Arquivo de skin inválido.");
        var config = Parse(File.ReadAllText(file)); config.Name = name; return config;
    }
    public static SkinConfig Parse(string json)
    {
        if (json == null || json.Length > 131072) throw new ArgumentException("Configuração de skin muito grande.");
        var cfg = JsonSerializer.Deserialize<SkinConfig>(json, Json) ?? throw new ArgumentException("Skin vazia.");
        // Preserve extension fields while normalizing legacy PascalCase and bounded numeric values.
        var defaults = new SkinConfig();
        foreach (var property in typeof(SkinConfig).GetProperties())
        {
            if (property.PropertyType == typeof(string) && property.GetValue(cfg) == null) property.SetValue(cfg, property.GetValue(defaults));
            if (property.PropertyType != typeof(double)) continue;
            double value = (double)property.GetValue(cfg);
            if (!double.IsFinite(value)) throw new ArgumentException("Número inválido na skin.");
            (double min, double max) = property.Name switch
            {
                "BackgroundPositionX" or "BackgroundPositionY" => (0, 100),
                "BackgroundBrightness" or "BackgroundSaturation" => (0, 200),
                "GradientAngle" => (0, 360), "ContentScale" => (80, 130), "SidebarWidth" => (56, 100),
                "ScrollbarWidth" => (4, 16), "BackgroundBlur" or "PanelBlur" or "BarBlur" => (0, 32),
                "PanelRadius" or "PanelPadding" or "ContentPadding" or "SidebarRadius" or "WindowRadius" or "ButtonRadius" or "CardRadius" or "CardPadding" or "CardGap" => (0, 48),
                _ => (0, 1)
            };
            property.SetValue(cfg, Math.Clamp(value, min, max));
        }
        cfg.BorderWidth = Math.Clamp(cfg.BorderWidth, 0, 4);
        cfg.SettingsColumns = Math.Clamp(cfg.SettingsColumns, 1, 2);
        if (!new[] { "image", "video", "color", "gradient" }.Contains(cfg.BackgroundType)) cfg.BackgroundType = "color";
        if (!new[] { "cover", "contain", "fill" }.Contains(cfg.BackgroundFit)) cfg.BackgroundFit = "cover";
        if (!new[] { "system", "segoe", "mono" }.Contains(cfg.FontFamily)) cfg.FontFamily = "system";
        if (!new[] { "left", "right", "bottom" }.Contains(cfg.NavigationPlacement)) cfg.NavigationPlacement = "left";
        if (!new[] { "left", "center", "right" }.Contains(cfg.ControlsPlacement)) cfg.ControlsPlacement = "right";
        if (!new[] { "floating", "filled" }.Contains(cfg.WindowPresentation)) cfg.WindowPresentation = "floating";
        if (!new[] { "glass", "liquid", "solid", "terminal", "ornate" }.Contains(cfg.SurfaceStyle)) cfg.SurfaceStyle = "glass";
        var navigationIds = new[] { "dashboard", "wuwa-db", "assets", "local-ai", "cloud", "stream", "hand-motion" };
        cfg.NavigationOrder = (cfg.NavigationOrder ?? new()).Where(id => navigationIds.Contains(id)).Distinct()
            .Concat(navigationIds.Where(id => cfg.NavigationOrder == null || !cfg.NavigationOrder.Contains(id))).ToList();
        var sectionIds = new[] { "behavior", "layout", "skins", "about" };
        cfg.SettingsSectionOrder = (cfg.SettingsSectionOrder ?? new()).Where(id => sectionIds.Contains(id)).Distinct()
            .Concat(sectionIds.Where(id => cfg.SettingsSectionOrder == null || !cfg.SettingsSectionOrder.Contains(id))).ToList();
        foreach (string url in new[] { cfg.BackgroundUrl, cfg.SidebarImage, cfg.TitlebarImage })
            if (url.Length > 4096 || (url != "" && (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))))
                throw new ArgumentException("Use uma URL HTTP/HTTPS ou importe o arquivo do computador.");
        foreach (var property in typeof(SkinConfig).GetProperties().Where(p => p.Name.EndsWith("Color") || p.Name == "PrimaryHover"))
        {
            var color = (string)property.GetValue(cfg);
            if (color.Length > 128 || color.IndexOfAny(new[] { ';', '{', '}', '<', '>' }) >= 0)
                throw new ArgumentException("Cor inválida.");
        }
        return cfg;
    }
    public void Save(string name, string json, bool allowDefault = false)
    {
        lock (sync) SaveCore(name, json, allowDefault);
    }
    private void SaveCore(string name, string json, bool allowDefault)
    {
        if (name.Equals("default", StringComparison.OrdinalIgnoreCase) && !allowDefault)
            throw new InvalidOperationException("Salve uma cópia pessoal para preservar a skin padrão nas atualizações.");
        var cfg = Parse(json); cfg.Name = name;
        string dir = DirectoryFor(name); Directory.CreateDirectory(dir);
        string path = Path.Combine(dir, "skin.json"), temp = Path.Combine(dir, Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("Arquivo de skin não pode ser um link.");
            File.WriteAllText(temp, JsonSerializer.Serialize(cfg, Json));
            if (File.Exists(path)) File.Replace(temp, path, null); else File.Move(temp, path);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    public SkinConfig Copy(string name, string source, string json)
    {
        lock (sync) return CopyCore(name, source, json);
    }
    private SkinConfig CopyCore(string name, string source, string json)
    {
        DirectoryFor(source);
        string dir = DirectoryFor(name);
        if (Directory.Exists(dir) || File.Exists(dir)) throw new IOException("Já existe uma skin com esse nome.");
        var cfg = Parse(json);
        Directory.CreateDirectory(dir);
        try
        {
            cfg.BackgroundUrl = CopyAsset(cfg.BackgroundUrl, name);
            cfg.SidebarImage = CopyAsset(cfg.SidebarImage, name);
            cfg.TitlebarImage = CopyAsset(cfg.TitlebarImage, name);
            cfg.Name = name; Save(name, JsonSerializer.Serialize(cfg, Json)); return cfg;
        }
        catch { Directory.Delete(dir, true); throw; } // Only the directory exclusively created above.
    }
    private string CopyAsset(string url, string target)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || !uri.Host.Equals("appassets", StringComparison.OrdinalIgnoreCase)) return url;
        var segments = uri.AbsolutePath.Split('/').Select(Uri.UnescapeDataString).ToArray();
        if (segments.Length != 5 || segments[1] != "skins" || segments[3] != "assets" ||
            segments[4] != Path.GetFileName(segments[4]) || segments[4].IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            throw new IOException("Referência local de imagem inválida.");
        string assetDir = Path.Combine(DirectoryFor(segments[2]), "assets"); SafeDirectory(assetDir);
        return Import(target, Path.Combine(assetDir, segments[4]));
    }
    public string Import(string name, string file)
    {
        lock (sync) return ImportCore(name, file);
    }
    private string ImportCore(string name, string file)
    {
        if (name.Equals("default", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Salve uma cópia antes de importar arquivos.");
        string dir = DirectoryFor(name);
        if (!File.Exists(Path.Combine(dir, "skin.json")) && !Directory.Exists(dir)) throw new IOException("Crie a skin primeiro.");
        string extension = Path.GetExtension(file).ToLowerInvariant();
        if (!new[] { ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".mp4", ".webm" }.Contains(extension))
            throw new ArgumentException("Formato de mídia não suportado.");
        var info = new FileInfo(file);
        if (!info.Exists || info.Length > 512L * 1024 * 1024 || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Arquivo ausente, link ou maior que 512 MiB.");
        string assets = Path.Combine(dir, "assets"); SafeDirectory(assets); Directory.CreateDirectory(assets);
        string leaf = Guid.NewGuid().ToString("N") + extension;
        File.Copy(file, Path.Combine(assets, leaf));
        return $"https://appassets/skins/{Uri.EscapeDataString(name)}/assets/{leaf}";
    }
}
