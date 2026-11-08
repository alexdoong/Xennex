using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;

namespace Xennex.Services.Gestures
{
    /// <summary>Imports usable legacy entries without modifying originals or blocking a new profile.</summary>
    internal static class GestureLegacyImporter
    {
        private static string Shortcut(string value)
        {
            var aliases = new Dictionary<string, string> {
                ["windows"] = "win", ["meta"] = "win", ["control"] = "ctrl", ["escape"] = "esc",
                ["arrowleft"] = "left", ["arrowright"] = "right", ["arrowup"] = "up", ["arrowdown"] = "down",
                ["return"] = "enter", ["del"] = "delete"
            };
            return string.Join("+", value.ToLowerInvariant().Split('+').Select(k => aliases.GetValueOrDefault(k.Trim(), k.Trim())));
        }
        private static JsonObject Read(string path, List<string> warnings)
        {
            try { return File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path)) as JsonObject : null; }
            catch (Exception error) { AppLog.Error("Gestures.Legacy", error); warnings.Add(Path.GetFileName(path) + " inválido"); return null; }
        }
        private static bool Valid(JsonObject profile, JsonObject gesture)
        {
            try
            {
                var candidate = (JsonObject)profile.DeepClone();
                candidate["gestures"] = new JsonArray(gesture.DeepClone());
                GestureProfileValidation.Validate(candidate);
                return true;
            }
            catch (Exception error) when (error is InvalidDataException or InvalidOperationException or FormatException)
            { return false; }
        }
        public static void Import(string directory, JsonObject profile)
        {
            var warnings = new List<string>();
            var legacy = Read(Path.Combine(directory, "gestures.json"), warnings);
            foreach (var item in legacy ?? new JsonObject())
            {
                if (profile["gestures"].AsArray().Count >= 40) { warnings.Add("limite de gestos atingido"); break; }
                if (item.Value is not JsonArray points || points.Count != 21) { warnings.Add("amostra antiga inválida"); continue; }
                var gesture = GestureProfileStore.Binding(Guid.NewGuid().ToString("N"),
                    "Importado: " + item.Key.Substring(0, Math.Min(60, item.Key.Length)), "pose", "none");
                string shortcut = item.Key switch {
                    "Play/Pause" => "playpause", "Volume Up" => "volumeup", "Volume Down" => "volumedown", "Mute" => "mute", _ => null
                };
                if (item.Key.StartsWith("KEYBOARD:")) shortcut = Shortcut(item.Key.Substring(9));
                if (shortcut != null) gesture["action"] = new JsonObject { ["type"] = "shortcut", ["value"] = shortcut };
                else if (item.Key == "MoveMouse") gesture["action"]["type"] = "pointer";
                else if (item.Key == "MoveWindow") gesture["action"]["type"] = "drag_window";
                gesture["enabled"] = false;
                gesture["samples"].AsArray().Add(new JsonObject { ["legacy"] = true, ["duration"] = 1, ["frames"] = new JsonArray(points.DeepClone()) });
                if (!Valid(profile, gesture))
                {
                    gesture["action"] = new JsonObject { ["type"] = "none", ["value"] = "" };
                    warnings.Add("ação ou amostra antiga requer revisão");
                }
                if (Valid(profile, gesture)) profile["gestures"].AsArray().Add(gesture);
            }
            var swipes = Read(Path.Combine(directory, "swipe_config.json"), warnings);
            foreach (var direction in new[] { "Left", "Right", "Up", "Down" })
            {
                if (swipes?["Swipe" + direction] is not JsonValue value || !value.TryGetValue<string>(out string action) || !action.StartsWith("KEYBOARD:")) continue;
                var target = profile["gestures"].AsArray().First(g => (string)g["id"] == direction.ToLowerInvariant());
                var candidate = (JsonObject)target.DeepClone();
                candidate["action"]["value"] = Shortcut(action.Substring(9));
                if (Valid(profile, candidate)) target["action"]["value"] = candidate["action"]["value"].DeepClone();
                else warnings.Add("atalho antigo de swipe inválido");
            }
            if (legacy != null || warnings.Count > 0)
                profile["migrationNotice"] = "Gestos antigos preservados nos arquivos originais. Poses importadas ficam desabilitadas para revisão."
                    + (warnings.Count > 0 ? " Itens que precisam de revisão: " + warnings.Count + "." : "");
            GestureProfileValidation.Validate(profile);
        }
    }
}
