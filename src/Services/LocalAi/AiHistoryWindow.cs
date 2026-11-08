using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

/// <summary>Select complete exchanges, not isolated old questions. Excerpts are explicit and auditable.</summary>
internal static class AiHistoryWindow
{
    internal sealed record Entry(AiMessage Source, string Role, string Content, bool Excerpt)
    {
        public int Bytes => Encoding.UTF8.GetByteCount(Content) + 32;
    }
    internal static List<AiMessage[]> Exchanges(IEnumerable<AiMessage> messages)
    {
        var groups = new List<AiMessage[]>();
        var current = new List<AiMessage>();
        foreach (var message in messages)
        {
            if (message.Role == "user")
            {
                if (current.Any(m => m.Role == "assistant")) groups.Add(current.ToArray());
                current.Clear();
            }
            current.Add(message);
        }
        if (current.Any(m => m.Role == "assistant")) groups.Add(current.ToArray());
        return groups;
    }
    internal static List<Entry> Select(IEnumerable<AiMessage[]> exchanges, string specialistId, int budget)
    {
        var result = new List<Entry>();
        foreach (var exchange in exchanges.Reverse())
        {
            if (result.Count + exchange.Length > 24) break;
            var entries = exchange.Select(m => Render(m, specialistId)).ToArray();
            int size = entries.Sum(e => e.Bytes);
            if (size <= budget)
            {
                result.AddRange(entries); budget -= size; continue;
            }
            // Prefer a labelled excerpt of the latest exchange over an unrelated older prompt.
            if (result.Count == 0 && budget >= entries.Length * 192)
            {
                int each = budget / entries.Length - 32;
                var excerpts = entries.Select(e => e with { Content = Fit(e.Content, each), Excerpt = Encoding.UTF8.GetByteCount(e.Content) > each }).ToArray();
                result.AddRange(excerpts);
            }
            break;
        }
        return result;
    }
    private static Entry Render(AiMessage message, string specialistId)
    {
        bool own = message.Role == "assistant" && message.AuthorId == specialistId;
        string content = message.Content;
        if (message.Role == "assistant" && !own)
            content = "[Contribuição de " + (message.AuthorName == "" ? "outro assistente" : message.AuthorName) + "]\n" + content;
        return new(message, own ? "assistant" : "user", content, false);
    }
    private static string Fit(string text, int maxBytes)
    {
        if (Encoding.UTF8.GetByteCount(text) <= maxBytes) return text;
        const string marker = "\n[... trecho omitido; mensagem integral no histórico ...]\n";
        int available = maxBytes - Encoding.UTF8.GetByteCount(marker);
        var runes = text.EnumerateRunes().ToArray();
        int headBudget = Math.Min(128, available / 4), tailBudget = available - headBudget;
        var head = new StringBuilder();
        int first = 0;
        while (first < runes.Length && headBudget >= runes[first].Utf8SequenceLength)
        { headBudget -= runes[first].Utf8SequenceLength; head.Append(runes[first++].ToString()); }
        int last = runes.Length;
        while (last > first && tailBudget >= runes[last - 1].Utf8SequenceLength)
        { tailBudget -= runes[--last].Utf8SequenceLength; }
        head.Append(marker);
        for (int i = last; i < runes.Length; i++) head.Append(runes[i].ToString());
        return head.ToString();
    }
}
