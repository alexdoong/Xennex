using System;
using System.IO;
using System.Text.Json;
using Xennex.Models;

namespace Xennex.Services;

public sealed class SkinService
{
    private readonly ConfigService config;
    private readonly SkinRepository repository;
    public SkinService(ConfigService configService)
    {
        config = configService;
        try
        {
            repository = new SkinRepository(Path.Combine(AppContext.BaseDirectory, "wwwroot", "skins"));
            if (!File.Exists(Path.Combine(repository.DirectoryFor("default"), "skin.json")))
                repository.Save("default", JsonSerializer.Serialize(new SkinConfig(), SkinRepository.Json), true);
        }
        catch (Exception error) { AppLog.Error("Skins.Initialize", error); throw; }
    }
    private T Logged<T>(string action, Func<T> operation)
    {
        try { return operation(); }
        catch (Exception error) { AppLog.Error("Skins." + action, error); throw; }
    }
    public string[] GetAvailableSkins() => Logged("List", repository.List);
    public string GetActiveSkinConfig() => GetSkinConfig(config.Config.ActiveSkin);
    public string GetSkinConfig(string name) => Logged("Read", () => JsonSerializer.Serialize(repository.Read(string.IsNullOrEmpty(name) ? "default" : name), SkinRepository.Json));
    public bool SaveSkinConfig(string name, string json) => Logged("Save", () => { repository.Save(name, json); return true; });
    public void SetActiveSkin(string name) => Logged("Activate", () =>
    {
        repository.Read(name); config.Config.ActiveSkin = name; config.SaveConfig(); return true;
    });
    public string SaveSkinAs(string name, string source, string json) => Logged("Copy", () =>
    {
        var copy = repository.Copy(name, source, json);
        SetActiveSkin(name);
        return JsonSerializer.Serialize(copy, SkinRepository.Json);
    });
    public bool CreateNewSkin(string name, string source)
    {
        SaveSkinAs(name, source, GetSkinConfig(source)); return true;
    }
    public string PickAndImportAsset(string name, string type) => Logged("Import", () =>
    {
        string file = null;
        System.Windows.Application.Current?.Dispatcher.Invoke(() =>
        {
            var dialog = new Microsoft.Win32.OpenFileDialog
            {
                Filter = type == "video" ? "Vídeo (*.mp4;*.webm)|*.mp4;*.webm" : "Imagem (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)|*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp"
            };
            if (dialog.ShowDialog() == true) file = dialog.FileName;
        });
        return file == null ? "" : repository.Import(name, file);
    });
    public void OpenSkinFolder() => Logged("Open", () =>
    {
        string dir = repository.DirectoryFor(config.Config.ActiveSkin);
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(dir) { UseShellExecute = true });
        return true;
    });
}
