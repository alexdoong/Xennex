using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;

namespace Xennex.Services.Assets.Metadata;

internal sealed record PromptTerm(string Text, string Source);

internal static class PromptTermExtractor
{
    public static List<PromptTerm> Extract(string metadata)
    {
        var result = new List<PromptTerm>();
        if (string.IsNullOrWhiteSpace(metadata) || metadata.Length > 2_000_000) return result;
        try
        {
            using var document = JsonDocument.Parse(metadata);
            if (!document.RootElement.TryGetProperty("fields", out var fields) || fields.ValueKind != JsonValueKind.Object) return result;
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (fields.TryGetProperty("prompt", out var prompt) && prompt.ValueKind == JsonValueKind.String)
                ExtractComfy(prompt.GetString(), result, seen);
            if (fields.TryGetProperty("positive", out var positive) && positive.ValueKind == JsonValueKind.String)
                AddTerms(positive.GetString(), "positive", result, seen);
            if (fields.TryGetProperty("negative", out var negative) && negative.ValueKind == JsonValueKind.String)
                AddTerms(negative.GetString(), "negative", result, seen);
            if (fields.TryGetProperty("parameters", out var parameters) && parameters.ValueKind == JsonValueKind.String)
                ExtractParameters(parameters.GetString(), result, seen);
        }
        catch (JsonException) { /* Files can contain arbitrary text instead of JSON. */ }
        return result;
    }

    private static void ExtractComfy(string prompt, List<PromptTerm> result, HashSet<string> seen)
    {
        if (string.IsNullOrWhiteSpace(prompt) || prompt.Length > 1_000_000) return;
        JsonDocument document;
        try { document = JsonDocument.Parse(prompt); }
        catch (JsonException) { return; }
        using (document)
        {
        if (document.RootElement.ValueKind != JsonValueKind.Object) return;
        var nodes = document.RootElement;
        foreach (var node in nodes.EnumerateObject())
        {
            if (node.Value.ValueKind != JsonValueKind.Object || !node.Value.TryGetProperty("class_type", out var type) ||
                type.ValueKind != JsonValueKind.String || type.GetString() is not ("KSampler" or "KSamplerAdvanced") ||
                !node.Value.TryGetProperty("inputs", out var inputs) || inputs.ValueKind != JsonValueKind.Object) continue;
            AddReferencedText(nodes, inputs, "positive", result, seen);
            AddReferencedText(nodes, inputs, "negative", result, seen);
        }
        }
    }

    private static void AddReferencedText(JsonElement nodes, JsonElement inputs, string source,
        List<PromptTerm> result, HashSet<string> seen)
    {
        if (!inputs.TryGetProperty(source, out var link) || link.ValueKind != JsonValueKind.Array || link.GetArrayLength() < 1) return;
        var reference = link[0].ValueKind switch
        {
            JsonValueKind.String => link[0].GetString(),
            JsonValueKind.Number => link[0].GetRawText(),
            _ => null
        };
        if (reference == null || !nodes.TryGetProperty(reference, out var node) || node.ValueKind != JsonValueKind.Object ||
            !node.TryGetProperty("class_type", out var type) || type.ValueKind != JsonValueKind.String || type.GetString() != "CLIPTextEncode" ||
            !node.TryGetProperty("inputs", out var textInputs) || !textInputs.TryGetProperty("text", out var text) ||
            text.ValueKind != JsonValueKind.String) return;
        AddTerms(text.GetString(), source, result, seen);
    }

    private static void ExtractParameters(string parameters, List<PromptTerm> result, HashSet<string> seen)
    {
        if (string.IsNullOrWhiteSpace(parameters)) return;
        var negative = parameters.IndexOf("Negative prompt:", StringComparison.OrdinalIgnoreCase);
        var settings = parameters.IndexOf("\nSteps:", StringComparison.OrdinalIgnoreCase);
        var positiveText = parameters[..Math.Min(negative >= 0 ? negative : parameters.Length,
            settings >= 0 ? settings : parameters.Length)];
        AddTerms(positiveText, "positive", result, seen);
        if (negative < 0) return;
        var start = negative + "Negative prompt:".Length;
        var end = settings >= start ? settings : parameters.Length;
        AddTerms(parameters[start..end], "negative", result, seen);
    }

    private static void AddTerms(string prompt, string source, List<PromptTerm> result, HashSet<string> seen)
    {
        if (string.IsNullOrWhiteSpace(prompt)) return;
        var count = 0;
        foreach (var fragment in prompt.Split(new[] { ',', '\n', '\r' }, StringSplitOptions.RemoveEmptyEntries))
        {
            if (count++ >= 150) break;
            var term = fragment.Trim().Trim('(', ')', '[', ']', ' ');
            var separator = term.LastIndexOf(':');
            if (separator > 0 && double.TryParse(term[(separator + 1)..], NumberStyles.Float,
                CultureInfo.InvariantCulture, out _)) term = term[..separator].Trim();
            if (term.Length is < 2 or > 100 || !seen.Add(source + "\0" + term)) continue;
            result.Add(new PromptTerm(term, source));
        }
    }
}
