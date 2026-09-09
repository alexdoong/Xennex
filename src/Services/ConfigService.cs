using System;
using System.Collections.Generic;
using System.IO;
using Xennex.Models;

namespace Xennex.Services
{
    public class ConfigService
    {
        private readonly string configPath;
        private readonly string buildSavePath;

        public AppConfig Config { get; private set; } = new AppConfig();
        public WuWaBuild Build { get; private set; } = new WuWaBuild();

        public ConfigService()
        {
            string baseDir = AppContext.BaseDirectory;
            string dataDir = Path.Combine(baseDir, "Data");
            if (!Directory.Exists(dataDir))
            {
                Directory.CreateDirectory(dataDir);
            }

            configPath = Path.Combine(dataDir, "config.txt");
            buildSavePath = Path.Combine(dataDir, "wuwa_build.txt");

            LoadConfig();
        }

        public event Action<string> OnLogReceived;
        public event Action OnConfigChanged;

        private void Log(string msg) => OnLogReceived?.Invoke(msg);

        public void LoadConfig()
        {
            try
            {
                if (!File.Exists(configPath))
                {
                    Log("[Controller] No config found.");
                    AutoDetectReal();
                    return;
                }

                var lines = File.ReadAllLines(configPath);
                if (lines.Length > 0 && File.Exists(lines[0].Trim()))
                {
                    Config.RealExePath = lines[0].Trim();
                    Log("[Controller] REAL path: " + Path.GetFileName(Config.RealExePath));
                }

                if (lines.Length > 1)
                {
                    foreach (var item in lines[1].Split(','))
                    {
                        ParseConfigItem(item.Trim());
                    }
                }

                if (string.IsNullOrEmpty(Config.RealExePath))
                {
                    AutoDetectReal();
                }
            }
            catch (Exception ex)
            {
                Log("[Config ERR] " + ex.Message);
            }
        }

        private void ParseConfigItem(string item)
        {
            if (string.IsNullOrWhiteSpace(item)) return;

            if (item.StartsWith("CloseToTray=", StringComparison.OrdinalIgnoreCase))
            {
                if (bool.TryParse(item.Substring("CloseToTray=".Length).Trim(), out bool val))
                    Config.CloseToTray = val;
                return;
            }
            if (item.StartsWith("AutoStart=", StringComparison.OrdinalIgnoreCase))
            {
                if (bool.TryParse(item.Substring("AutoStart=".Length).Trim(), out bool val))
                    Config.AutoStart = val;
                return;
            }
            if (item.StartsWith("HideSidebarPullTab=", StringComparison.OrdinalIgnoreCase))
            {
                if (bool.TryParse(item.Substring("HideSidebarPullTab=".Length).Trim(), out bool val))
                    Config.HideSidebarPullTab = val;
                return;
            }
            if (item.StartsWith("SidebarPosition=", StringComparison.OrdinalIgnoreCase))
            {
                Config.SidebarPosition = item.Substring("SidebarPosition=".Length).Trim();
                return;
            }
            if (item.StartsWith("SidebarMonitor=", StringComparison.OrdinalIgnoreCase) && int.TryParse(item.Substring("SidebarMonitor=".Length).Trim(), out int sm))
            {
                Config.SidebarMonitorIndex = sm;
                return;
            }
            if (item.StartsWith("HandMotionCameraIndex=", StringComparison.OrdinalIgnoreCase) && int.TryParse(item.Substring("HandMotionCameraIndex=".Length).Trim(), out int hm))
            {
                Config.HandMotionCameraIndex = hm;
                return;
            }
            if (item.StartsWith("WindowLeft=", StringComparison.OrdinalIgnoreCase) && double.TryParse(item.Substring("WindowLeft=".Length).Trim(), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out double wl))
            {
                Config.WindowLeft = wl;
                return;
            }
            if (item.StartsWith("WindowTop=", StringComparison.OrdinalIgnoreCase) && double.TryParse(item.Substring("WindowTop=".Length).Trim(), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out double wt))
            {
                Config.WindowTop = wt;
                return;
            }
            if (item.StartsWith("AutoHideSidebar=", StringComparison.OrdinalIgnoreCase))
            {
                if (bool.TryParse(item.Substring("AutoHideSidebar=".Length).Trim(), out bool val))
                    Config.AutoHideSidebar = val;
                return;
            }
            if (item.StartsWith("AutoHideTitlebar=", StringComparison.OrdinalIgnoreCase))
            {
                if (bool.TryParse(item.Substring("AutoHideTitlebar=".Length).Trim(), out bool val))
                    Config.AutoHideTitlebar = val;
                return;
            }
            if (item.StartsWith("ActiveSkin=", StringComparison.OrdinalIgnoreCase))
            {
                Config.ActiveSkin = item.Substring("ActiveSkin=".Length).Trim();
                return;
            }
        }

        public void SaveConfig()
        {
            try
            {
                string line2 = string.Format(System.Globalization.CultureInfo.InvariantCulture,
                    "CloseToTray={0},AutoStart={1},SidebarMonitor={2},HideSidebarPullTab={3},SidebarPosition={4},HandMotionCameraIndex={5},WindowLeft={6},WindowTop={7},AutoHideSidebar={8},AutoHideTitlebar={9}",
                    Config.CloseToTray ? "true" : "false",
                    Config.AutoStart ? "true" : "false",
                    Config.SidebarMonitorIndex,
                    Config.HideSidebarPullTab ? "true" : "false",
                    Config.SidebarPosition,
                    Config.HandMotionCameraIndex,
                    Config.WindowLeft,
                    Config.WindowTop,
                    Config.AutoHideSidebar ? "true" : "false",
                    Config.AutoHideTitlebar ? "true" : "false");

                File.WriteAllLines(configPath, new[] { Config.RealExePath, line2 });
                OnConfigChanged?.Invoke();
            }
            catch (Exception ex)
            {
                Log($"[Config SAVE ERR] {ex.Message}");
            }
        }

        public void AutoDetectReal()
        {
            string found = ScanForReal();
            if (!string.IsNullOrEmpty(found))
            {
                Config.RealExePath = found;
                SaveConfig();
                Log("[Controller] Auto-located: " + Config.RealExePath);
                return;
            }

            Log("[Controller] REAL.exe not found – set in Settings.");
        }

        private string ScanForReal()
        {
            string dir = AppContext.BaseDirectory;
            string[] paths = {
                "REAL.exe", "real.exe", "real-app.exe",
                @"..\REAL-updater-v2\REAL-updater-v2\real-app\build\Debug\real-app.exe",
                @"..\REAL-updater-v2\REAL-updater-v2\real-app\build\Release\real-app.exe"
            };

            foreach (var rel in paths)
            {
                try
                {
                    string f = Path.GetFullPath(Path.Combine(dir, rel));
                    if (File.Exists(f)) return f;
                }
                catch (Exception ex)
                {
                    Log($"[ScanForReal Path ERR] {ex.Message}");
                }
            }

            try
            {
                foreach (var f in Directory.GetFiles(dir, "*real*.exe", SearchOption.AllDirectories))
                {
                    string n = Path.GetFileName(f).ToLower();
                    if (!n.Contains("controller")) return f;
                }
            }
            catch (Exception ex)
            {
                Log($"[ScanForReal Dir ERR] {ex.Message}");
            }

            return null;
        }

        public void LoadWuWaBuild(Action<string, string, Dictionary<int, string>> onPathsLoaded)
        {
            if (!File.Exists(buildSavePath)) return;

            try
            {
                var echoPaths = new Dictionary<int, string>();
                string charImagePath = null;
                string weaponImagePath = null;

                foreach (var line in File.ReadAllLines(buildSavePath))
                {
                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;

                    string key = line.Substring(0, eq).Trim();
                    string val = line.Substring(eq + 1).Trim();

                    switch (key)
                    {
                        case "Name":         Build.ResonatorName = val; break;
                        case "Level":        Build.Level = val; break;
                        case "Element":      Build.Element = val; break;
                        case "Seq":          int.TryParse(val, out Build.Sequence); break;
                        case "CharImage":    if (File.Exists(val)) { Build.CharImagePath = val; charImagePath = val; } break;
                        case "ImgPanX":      int.TryParse(val, out Build.ImagePanX); break;
                        case "ImgPanY":      int.TryParse(val, out Build.ImagePanY); break;
                        case "ImgScale":     float.TryParse(val, out Build.ImageScale); break;
                        case "WeaponName":   Build.WeaponName = val; break;
                        case "WeaponRarity": int.TryParse(val, out Build.WeaponRarity); break;
                        case "WeaponRef":    int.TryParse(val, out Build.WeaponRefinement); break;
                        case "WeaponLevel":  Build.WeaponLevel = val; break;
                        case "WeaponImage":  if (File.Exists(val)) { Build.WeaponImagePath = val; weaponImagePath = val; } break;
                        case "HP":           Build.StatHP = val; break;
                        case "ATK":          Build.StatATK = val; break;
                        case "DEF":          Build.StatDEF = val; break;
                        case "CritRate":     Build.StatCritRate = val; break;
                        case "CritDMG":      Build.StatCritDMG = val; break;
                        case "EnergyRegen":  Build.StatEnergyRegen = val; break;
                        case "SklDMG":       Build.StatSklDMG = val; break;
                        default:
                            ParseEchoProperty(key, val, echoPaths);
                            break;
                    }
                }

                onPathsLoaded?.Invoke(charImagePath, weaponImagePath, echoPaths);
            }
            catch (Exception ex)
            {
                Log($"[WuWaBuild LOAD ERR] {ex.Message}");
            }
        }

        private void ParseEchoProperty(string key, string val, Dictionary<int, string> echoPaths)
        {
            if (key.Length < 2 || key[0] != 'E' || !char.IsDigit(key[1])) return;

            int ei = key[1] - '0';
            if (ei < 0 || ei >= 5) return;

            string sub = key.Length > 2 ? key.Substring(2) : "";
            if (sub == "Image" && File.Exists(val))
            {
                Build.Echoes[ei].ImagePath = val;
                echoPaths[ei] = val;
                return;
            }

            if (sub == "Main")
            {
                var parts = val.Split('|');
                Build.Echoes[ei].MainStatName = parts.Length > 0 ? parts[0] : "";
                Build.Echoes[ei].MainStatValue = parts.Length > 1 ? parts[1] : "";
                return;
            }

            if (sub.Length < 2 || sub[0] != 'S' || !char.IsDigit(sub[1])) return;

            int si = sub[1] - '0';
            if (si < 0 || si >= 5) return;

            var p = val.Split('|');
            Build.Echoes[ei].Substats[si].Name = p.Length > 0 ? p[0] : "";
            Build.Echoes[ei].Substats[si].Value = p.Length > 1 ? p[1] : "";
            int.TryParse(p.Length > 2 ? p[2] : "0", out int quality);
            Build.Echoes[ei].Substats[si].Quality = quality;
        }

        public void SaveWuWaBuild()
        {
            try
            {
                var lines = new List<string>
                {
                    "Name=" + Build.ResonatorName,
                    "Level=" + Build.Level,
                    "Element=" + Build.Element,
                    "Seq=" + Build.Sequence,
                    "CharImage=" + Build.CharImagePath,
                    "ImgPanX=" + Build.ImagePanX,
                    "ImgPanY=" + Build.ImagePanY,
                    "ImgScale=" + Build.ImageScale.ToString("F2"),
                    "WeaponName=" + Build.WeaponName,
                    "WeaponRarity=" + Build.WeaponRarity,
                    "WeaponRef=" + Build.WeaponRefinement,
                    "WeaponLevel=" + Build.WeaponLevel,
                    "WeaponImage=" + Build.WeaponImagePath,
                    "HP=" + Build.StatHP,
                    "ATK=" + Build.StatATK,
                    "DEF=" + Build.StatDEF,
                    "CritRate=" + Build.StatCritRate,
                    "CritDMG=" + Build.StatCritDMG,
                    "EnergyRegen=" + Build.StatEnergyRegen,
                    "SklDMG=" + Build.StatSklDMG
                };

                for (int i = 0; i < 5; i++)
                {
                    var echo = Build.Echoes[i];
                    lines.Add(string.Format("E{0}Image={1}", i, echo.ImagePath));
                    lines.Add(string.Format("E{0}Main={1}|{2}", i, echo.MainStatName, echo.MainStatValue));
                    for (int j = 0; j < 5; j++)
                    {
                        lines.Add(string.Format("E{0}S{1}={2}|{3}|{4}", i, j,
                            echo.Substats[j].Name, echo.Substats[j].Value, echo.Substats[j].Quality));
                    }
                }

                File.WriteAllLines(buildSavePath, lines);
            }
            catch (Exception ex)
            {
                Log($"[WuWaBuild SAVE ERR] {ex.Message}");
            }
        }
    }
}
