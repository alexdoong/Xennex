using System;
using System.Collections.Generic;
using System.IO;

namespace WacomRealController
{
    public class ConfigService
    {
        private readonly string configPath = "config.txt";
        private readonly string buildSavePath = "wuwa_build.txt";

        public AppConfig Config { get; private set; } = new AppConfig();
        public WuWaBuild Build { get; private set; } = new WuWaBuild();

        public event Action<string> OnLogReceived;

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
                        if (item == "CloseToTray=false") Config.CloseToTray = false;
                        if (item == "AutoStart=true")    Config.AutoStart = true;
                        if (item.StartsWith("SidebarMonitor="))
                        {
                            int val;
                            if (int.TryParse(item.Substring("SidebarMonitor=".Length), out val))
                                Config.SidebarMonitorIndex = val;
                        }
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

        public void SaveConfig()
        {
            try
            {
                string line2 = string.Format("CloseToTray={0},AutoStart={1},SidebarMonitor={2}",
                    Config.CloseToTray ? "true" : "false",
                    Config.AutoStart ? "true" : "false",
                    Config.SidebarMonitorIndex);
                File.WriteAllLines(configPath, new[] { Config.RealExePath, line2 });
            }
            catch { }
        }

        public void AutoDetectReal()
        {
            string found = ScanForReal();
            if (!string.IsNullOrEmpty(found))
            {
                Config.RealExePath = found;
                SaveConfig();
                Log("[Controller] Auto-located: " + Config.RealExePath);
            }
            else
            {
                Log("[Controller] REAL.exe not found – set in Settings.");
            }
        }

        private string ScanForReal()
        {
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            string[] paths = {
                "REAL.exe", "real.exe", "real-app.exe",
                @"..\REAL-updater-v2\REAL-updater-v2\real-app\build\Debug\real-app.exe",
                @"..\REAL-updater-v2\REAL-updater-v2\real-app\build\Release\real-app.exe"
            };
            foreach (var rel in paths)
            {
                try { string f = Path.GetFullPath(Path.Combine(dir, rel)); if (File.Exists(f)) return f; } catch { }
            }
            try
            {
                foreach (var f in Directory.GetFiles(dir, "*real*.exe", SearchOption.AllDirectories))
                {
                    string n = Path.GetFileName(f).ToLower();
                    if (!n.Contains("controller")) return f;
                }
            }
            catch { }
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
                            if (key.Length >= 2 && key[0] == 'E' && char.IsDigit(key[1]))
                            {
                                int ei = key[1] - '0';
                                if (ei >= 0 && ei < 5)
                                {
                                    string sub = key.Length > 2 ? key.Substring(2) : "";
                                    if (sub == "Image" && File.Exists(val)) { Build.Echoes[ei].ImagePath = val; echoPaths[ei] = val; }
                                    else if (sub == "Main") { var p = val.Split('|'); Build.Echoes[ei].MainStatName = p.Length > 0 ? p[0] : ""; Build.Echoes[ei].MainStatValue = p.Length > 1 ? p[1] : ""; }
                                    else if (sub.Length >= 2 && sub[0] == 'S' && char.IsDigit(sub[1]))
                                    {
                                        int si = sub[1] - '0';
                                        if (si >= 0 && si < 5)
                                        {
                                            var p = val.Split('|');
                                            Build.Echoes[ei].Substats[si].Name  = p.Length > 0 ? p[0] : "";
                                            Build.Echoes[ei].Substats[si].Value = p.Length > 1 ? p[1] : "";
                                            int q = 0; int.TryParse(p.Length > 2 ? p[2] : "0", out q);
                                            Build.Echoes[ei].Substats[si].Quality = q;
                                        }
                                    }
                                }
                            }
                            break;
                    }
                }
                onPathsLoaded?.Invoke(charImagePath, weaponImagePath, echoPaths);
            }
            catch { }
        }

        public void SaveWuWaBuild()
        {
            try
            {
                var lines = new List<string>();
                lines.Add("Name=" + Build.ResonatorName);
                lines.Add("Level=" + Build.Level);
                lines.Add("Element=" + Build.Element);
                lines.Add("Seq=" + Build.Sequence);
                lines.Add("CharImage=" + Build.CharImagePath);
                lines.Add("ImgPanX=" + Build.ImagePanX);
                lines.Add("ImgPanY=" + Build.ImagePanY);
                lines.Add("ImgScale=" + Build.ImageScale.ToString("F2"));
                lines.Add("WeaponName=" + Build.WeaponName);
                lines.Add("WeaponRarity=" + Build.WeaponRarity);
                lines.Add("WeaponRef=" + Build.WeaponRefinement);
                lines.Add("WeaponLevel=" + Build.WeaponLevel);
                lines.Add("WeaponImage=" + Build.WeaponImagePath);
                lines.Add("HP=" + Build.StatHP);
                lines.Add("ATK=" + Build.StatATK);
                lines.Add("DEF=" + Build.StatDEF);
                lines.Add("CritRate=" + Build.StatCritRate);
                lines.Add("CritDMG=" + Build.StatCritDMG);
                lines.Add("EnergyRegen=" + Build.StatEnergyRegen);
                lines.Add("SklDMG=" + Build.StatSklDMG);
                for (int i = 0; i < 5; i++)
                {
                    var echo = Build.Echoes[i];
                    lines.Add(string.Format("E{0}Image={1}", i, echo.ImagePath));
                    lines.Add(string.Format("E{0}Main={1}|{2}", i, echo.MainStatName, echo.MainStatValue));
                    for (int j = 0; j < 5; j++)
                        lines.Add(string.Format("E{0}S{1}={2}|{3}|{4}", i, j,
                            echo.Substats[j].Name, echo.Substats[j].Value, echo.Substats[j].Quality));
                }
                File.WriteAllLines(buildSavePath, lines);
            }
            catch { }
        }
    }
}
