using System;
using System.IO;
using System.Text.Json;
using Xennex.Services;

string root = Path.Combine(Path.GetTempPath(), "XennexSkinTests-" + Guid.NewGuid().ToString("N"));
int checks = 0;
void Check(bool value, string name) { if (!value) throw new Exception(name); Console.WriteLine("PASS " + name); checks++; }
void Reject(Action action, string name) { bool rejected = false; try { action(); } catch { rejected = true; } Check(rejected, name); }
try
{
    var store = new SkinRepository(root);
    store.Save("default", """{"primaryColor":"#123456","panelRadius":19,"customSetting":{"hello":true}}""", true);
    Reject(() => store.Save("default", "{}"), "Default cannot be overwritten");
    var copy = store.Copy("Teste pessoal", "default", JsonSerializer.Serialize(store.Read("default"), SkinRepository.Json));
    Check(copy.PrimaryColor == "#123456" && copy.PanelRadius == 19, "CamelCase properties survive cloning");
    Check(copy.Extra["customSetting"].GetProperty("hello").GetBoolean(), "Unknown properties survive cloning");
    Reject(() => store.Copy("Teste pessoal", "default", "{}"), "Duplicate name does not overwrite");
    foreach (var name in new[] { "../outside", "CON", "CON.json", "bad.", " bad", "x/y", "x\\y", "..", "x:y" })
        Reject(() => store.DirectoryFor(name), "Reject invalid name " + name);
    string sourceFile = Path.Combine(root, "sample.png"); File.WriteAllBytes(sourceFile, new byte[] { 1, 2, 3 });
    string url = store.Import("Teste pessoal", sourceFile);
    Check(url.Contains("Teste%20pessoal"), "Local URL escapes spaces");
    copy.BackgroundUrl = url;
    store.Save(copy.Name, JsonSerializer.Serialize(copy, SkinRepository.Json));
    var second = store.Copy("Outra skin", copy.Name, JsonSerializer.Serialize(copy, SkinRepository.Json));
    string clonedPath = Path.Combine(root, "Outra skin", "assets", Path.GetFileName(new Uri(second.BackgroundUrl).LocalPath));
    Check(File.Exists(clonedPath), "Clone owns its referenced media");
    Directory.Delete(Path.Combine(root, "Teste pessoal"), true);
    Check(File.ReadAllBytes(clonedPath).Length == 3, "Clone remains usable without source skin");
    string original = File.ReadAllText(Path.Combine(root, "Outra skin", "skin.json"));
    Reject(() => store.Save("Outra skin", """{"backgroundUrl":"javascript:alert(1)"}"""), "Reject unsupported URL");
    Reject(() => store.Save("Outra skin", "{broken"), "Reject malformed JSON");
    Check(original == File.ReadAllText(Path.Combine(root, "Outra skin", "skin.json")), "Failed save preserves file");
    var bounded = SkinRepository.Parse("""{"ContentScale":999,"PanelOpacity":-1,"SidebarWidth":-500,"BackgroundFit":"bad"}""");
    Check(bounded.ContentScale == 130 && bounded.PanelOpacity == 0 && bounded.SidebarWidth == 56 && bounded.BackgroundFit == "cover", "Legacy PascalCase and bounds");
    var layout = SkinRepository.Parse("""{"navigationPlacement":"bottom","controlsPlacement":"center","windowPresentation":"filled","surfaceStyle":"terminal"}""");
    Check(layout.NavigationPlacement == "bottom" && layout.ControlsPlacement == "center" && layout.WindowPresentation == "filled" && layout.SurfaceStyle == "terminal", "Layout choices parse");
    var liquid = SkinRepository.Parse("""{"surfaceStyle":"liquid","glassHighlight":0.55}""");
    Check(liquid.SurfaceStyle == "liquid" && liquid.GlassHighlight == .55, "Liquid Glass choices parse");
    Check(SkinRepository.Parse("{}").GlassHighlight == .35, "Legacy skins get safe reflection default");
    Check(SkinRepository.Parse("""{"GlassHighlight":99}""").GlassHighlight == 1 && SkinRepository.Parse("""{"glassHighlight":-1}""").GlassHighlight == 0, "Reflection intensity is bounded");
    var invalidLayout = SkinRepository.Parse("""{"navigationPlacement":"outside","controlsPlacement":"hidden","windowPresentation":"unknown","surfaceStyle":"script"}""");
    Check(invalidLayout.NavigationPlacement == "left" && invalidLayout.ControlsPlacement == "right" && invalidLayout.WindowPresentation == "floating" && invalidLayout.SurfaceStyle == "glass", "Invalid layout falls back safely");
    var ordered = SkinRepository.Parse("""{"navigationOrder":["assets","assets","unknown","dashboard"]}""");
    Check(ordered.NavigationOrder[0] == "assets" && ordered.NavigationOrder[1] == "dashboard" && ordered.NavigationOrder.Count == 7, "Navigation order is unique and complete");
    var cards = SkinRepository.Parse("""{"cardPadding":999,"cardGap":-1,"settingsColumns":8,"settingsSectionOrder":["skins","skins","unknown","behavior"]}""");
    Check(cards.CardPadding == 48 && cards.CardGap == 0 && cards.SettingsColumns == 2 && cards.SettingsSectionOrder[0] == "skins" && cards.SettingsSectionOrder.Count == 4, "Card bounds and section order normalize");
    second.NavigationPlacement = "bottom"; second.ControlsPlacement = "center"; second.WindowPresentation = "filled"; second.SurfaceStyle = "terminal";
    second.NavigationOrder = ordered.NavigationOrder;
    second.CardColor = "#123456"; second.SettingsColumns = 2; second.SettingsSectionOrder = cards.SettingsSectionOrder;
    store.Save("Outra skin", JsonSerializer.Serialize(second, SkinRepository.Json));
    var reopened = new SkinRepository(root).Read("Outra skin");
    Check(reopened.PrimaryColor == "#123456" && reopened.Name == "Outra skin" && reopened.NavigationPlacement == "bottom" && reopened.SurfaceStyle == "terminal" && reopened.NavigationOrder[0] == "assets" && reopened.SettingsColumns == 2 && reopened.SettingsSectionOrder[0] == "skins", "Reload preserves saved values");
    second.SurfaceStyle = "liquid"; second.GlassHighlight = .55;
    store.Save("Outra skin", JsonSerializer.Serialize(second, SkinRepository.Json));
    var savedLiquid = new SkinRepository(root).Read("Outra skin");
    Check(savedLiquid.SurfaceStyle == "liquid" && savedLiquid.GlassHighlight == .55 && savedLiquid.Extra.ContainsKey("customSetting"), "Liquid Glass persists without losing extension fields");
    Reject(() => store.Copy("Falha", "default", """{"backgroundUrl":"https://appassets/skins/default/assets/missing.png"}"""), "Missing asset fails cloning");
    Check(!Directory.Exists(Path.Combine(root,"Falha")), "Failed clone leaves no incomplete skin");
    Console.WriteLine(checks + " skin checks passed");
}
finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
