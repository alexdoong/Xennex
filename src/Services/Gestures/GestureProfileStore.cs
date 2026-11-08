using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Xennex.Services.Gestures
{
    /// <summary>Single writer for mappings and landmark samples; never stores camera images.</summary>
    public sealed class GestureProfileStore
    {
        private readonly object sync = new();
        public string FilePath { get; }
        private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };
        public GestureProfileStore(string directory) { FilePath = Path.Combine(directory, "gesture_profiles.json"); }
        internal static JsonObject Binding(string id, string name, string source, string action, string value = "") => new()
        {
            ["id"] = id, ["name"] = name, ["source"] = source, ["enabled"] = true,
            ["holdMs"] = 220, ["cooldownMs"] = 1000, ["threshold"] = 0.22,
            ["action"] = new JsonObject { ["type"] = action, ["value"] = value }, ["samples"] = new JsonArray()
        };
        private static JsonObject Defaults() => new()
        {
            ["version"] = 1, ["hand"] = "Any", ["preview"] = false, ["smoothing"] = 0.45,
            ["swipeThreshold"] = 0.18, ["dragTarget"] = "titlebar",
            ["gestures"] = new JsonArray(
                Binding("pointer", "Indicador: mover cursor", "point", "pointer"),
                Binding("pinch", "Pinch: segurar janela", "pinch", "drag_window"),
                Binding("left", "Swipe para esquerda", "swipe_left", "shortcut", "win+left"),
                Binding("right", "Swipe para direita", "swipe_right", "shortcut", "win+right"),
                Binding("up", "Swipe para cima", "swipe_up", "shortcut", "win+up"),
                Binding("down", "Swipe para baixo", "swipe_down", "shortcut", "win+down"))
        };
        public JsonObject Read()
        {
            lock (sync)
            {
                try
                {
                    if (!File.Exists(FilePath))
                    {
                        var defaults = Defaults();
                        GestureLegacyImporter.Import(Path.GetDirectoryName(FilePath), defaults);
                        Write(defaults);
                    }
                    var result = JsonNode.Parse(File.ReadAllText(FilePath)) as JsonObject ?? throw new InvalidDataException("Perfil inválido.");
                    GestureProfileValidation.Validate(result);
                    return result;
                }
                catch (Exception error) { AppLog.Error("Gestures.Profile.Read", error); throw; }
            }
        }
        public void Save(string json)
        {
            lock (sync)
            {
                try
                {
                    if (json.Length > 5_000_000) throw new InvalidDataException("Perfil muito grande.");
                    var next = JsonNode.Parse(json) as JsonObject ?? throw new InvalidDataException("Perfil inválido.");
                    var existing = Read()["gestures"].AsArray();
                    foreach (var gesture in next["gestures"]?.AsArray() ?? throw new InvalidDataException("Gestos ausentes."))
                    {
                        var old = existing.FirstOrDefault(g => (string)g["id"] == (string)gesture["id"]);
                        // UI edits mappings; recorded samples are merged from the latest disk state.
                        gesture["samples"] = old != null && (string)old["source"] == (string)gesture["source"]
                            ? old["samples"].DeepClone() : new JsonArray();
                    }
                    GestureProfileValidation.Validate(next);
                    Write(next);
                }
                catch (Exception error) { AppLog.Error("Gestures.Profile.Save", error); throw; }
            }
        }
        public void AddSample(string id, JsonNode sample)
        {
            lock (sync)
            {
                var profile = Read();
                var gesture = profile["gestures"].AsArray().FirstOrDefault(g => (string)g["id"] == id);
                if (gesture == null || !new[] { "pose", "motion" }.Contains((string)gesture["source"])) return;
                var samples = gesture["samples"].AsArray();
                if (samples.Count >= 8) throw new InvalidDataException("Limite de oito amostras. Limpe as amostras para gravar novamente.");
                samples.Add(sample.DeepClone());
                GestureProfileValidation.Validate(profile);
                Write(profile);
            }
        }
        public void ClearSamples(string id)
        {
            lock (sync)
            {
                var profile = Read();
                var gesture = profile["gestures"].AsArray().FirstOrDefault(g => (string)g["id"] == id);
                if (gesture == null) return;
                gesture["samples"] = new JsonArray();
                Write(profile);
            }
        }
        private void Write(JsonObject profile)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(FilePath));
                var temporary = FilePath + ".tmp";
                File.WriteAllText(temporary, profile.ToJsonString(Options));
                if (File.Exists(FilePath)) File.Replace(temporary, FilePath, FilePath + ".bak");
                else File.Move(temporary, FilePath);
            }
            catch (Exception error) { AppLog.Error("Gestures.Profile.Write", error); throw; }
        }
    }
}
