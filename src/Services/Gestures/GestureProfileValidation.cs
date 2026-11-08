using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
namespace Xennex.Services.Gestures
{
    internal static class GestureProfileValidation
    {
        private static readonly string[] Sources = { "pinch", "point", "open_palm", "swipe_left", "swipe_right", "swipe_up", "swipe_down", "pose", "motion" };
        private static readonly string[] Actions = { "none", "shortcut", "pointer", "drag_window", "drag_mouse", "scroll", "click", "right_click", "double_click" };

        private static void Range(JsonNode value, double minimum, double maximum)
        {
            double number = (value == null ? null : JsonSerializer.Deserialize<double?>(value.ToJsonString())) ?? double.NaN;
            if (!double.IsFinite(number) || number < minimum || number > maximum) throw new InvalidDataException("Parâmetro numérico inválido.");
        }
        public static void Validate(JsonObject profile)
        {
            if ((int?)profile["version"] != 1) throw new InvalidDataException("Versão de perfil não suportada.");
            if (!new[] { "Any", "Left", "Right" }.Contains((string)profile["hand"])) throw new InvalidDataException("Mão inválida.");
            if (!new[] { "titlebar", "foreground" }.Contains((string)profile["dragTarget"])) throw new InvalidDataException("Alvo de arraste inválido.");
            _ = profile["preview"].GetValue<bool>();
            Range(profile["smoothing"], 0, 0.9); Range(profile["swipeThreshold"], 0.08, 0.5);
            var gestures = profile["gestures"]?.AsArray() ?? throw new InvalidDataException("Gestos ausentes.");
            if (gestures.Count > 40) throw new InvalidDataException("Limite de 40 gestos.");
            var ids = new System.Collections.Generic.HashSet<string>();
            foreach (var gesture in gestures)
            {
                string id = (string)gesture?["id"] ?? "";
                if (!Regex.IsMatch(id, "^[a-zA-Z0-9_-]{1,80}$") || !ids.Add(id)) throw new InvalidDataException("ID repetido ou inválido.");
                string name = (string)gesture["name"] ?? "";
                if (string.IsNullOrWhiteSpace(name) || name.Length > 80) throw new InvalidDataException("Informe um nome para cada gesto (até 80 caracteres).");
                string source = (string)gesture["source"], action = (string)gesture["action"]?["type"];
                if (!Sources.Contains(source) || !Actions.Contains(action)) throw new InvalidDataException("Gesto ou ação não suportado.");
                _ = gesture["enabled"].GetValue<bool>();
                Range(gesture["holdMs"], 100, 2000); Range(gesture["cooldownMs"], 250, 5000); Range(gesture["threshold"], 0.05, 0.5);
                if ((source.StartsWith("swipe_") || source == "motion") && new[] { "pointer", "drag_window", "drag_mouse", "scroll" }.Contains(action))
                    throw new InvalidDataException("Movimentos usam ações pontuais; associe ações contínuas a uma pose, indicador ou pinch.");
                string value = (string)gesture["action"]?["value"] ?? "";
                if (action == "shortcut")
                {
                    string key = "(?:win|ctrl|alt|shift|left|right|up|down|enter|esc|space|tab|backspace|delete|home|end|pageup|pagedown|playpause|volumeup|volumedown|mute|f(?:[1-9]|1[0-9]|2[0-4])|[a-z0-9])";
                    if (!Regex.IsMatch(value, "^" + key + "(?:\\+" + key + "){0,4}$")) throw new InvalidDataException("Atalho inválido. Exemplo: win+left.");
                    if (value.Split('+').Distinct().Count() != value.Split('+').Length) throw new InvalidDataException("Atalho contém teclas repetidas.");
                }
                var samples = gesture["samples"]?.AsArray() ?? throw new InvalidDataException("Amostras ausentes.");
                if (samples.Count > 8) throw new InvalidDataException("Limite de oito amostras por gesto.");
                foreach (var sample in samples)
                {
                    Range(sample["duration"], 0.1, 3);
                    var frames = sample["frames"].AsArray();
                    if (frames.Count < 1 || frames.Count > 32) throw new InvalidDataException("Amostra inválida.");
                    int dimensions = (bool?)sample["legacy"] == true ? 2 : 3;
                    foreach (var frame in frames)
                    {
                        if (frame.AsArray().Count != 21) throw new InvalidDataException("Amostra deve conter 21 pontos.");
                        foreach (var point in frame.AsArray())
                        {
                            if (point.AsArray().Count != dimensions) throw new InvalidDataException("Dimensão inválida.");
                            foreach (var axis in point.AsArray()) Range(axis, -10, 10);
                        }
                    }
                }
            }
        }
    }
}
