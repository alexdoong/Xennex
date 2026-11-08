using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Xennex.Models.Assets;

namespace Xennex.Services.Assets;

// Declarative filename template; never evaluates expressions supplied by the UI.
internal sealed class AssetNamingSequence
{
    private readonly string template;
    private readonly int digits;
    private int number;
    public int StartNumber { get; }

    public AssetNamingSequence(AssetNamingRule rule, IEnumerable<string> folders)
    {
        if (rule == null || rule.BaseName == null || rule.BaseName.Length is < 1 or > 100 ||
            rule.Pattern == null || rule.Pattern.Length > 120 || rule.Scope is not ("all" or "conflicts") ||
            rule.Digits is < 1 or > 9 || rule.StartNumber is < 0 or > 999999999)
            throw new ArgumentException("Regra de nomes inválida.");
        AssetFileService.ValidateName(rule.BaseName);
        if (rule.Pattern.Split("{base}").Length != 2 || rule.Pattern.Split("{number}").Length != 2 ||
            rule.Pattern.Replace("{base}", "").Replace("{number}", "").IndexOfAny(new[] { '{', '}' }) >= 0)
            throw new ArgumentException("Use uma vez {base} e uma vez {number} no padrão.");
        template = rule.Pattern.Replace("{base}", rule.BaseName);
        AssetFileService.ValidateName(template.Replace("{number}", "1") + ".png");
        digits = rule.Digits;
        var last = rule.AutoContinue ? LastNumber(folders) : rule.StartNumber - 1;
        if (last >= 999999999) throw new ArgumentException("A numeração excedeu o limite permitido.");
        number = StartNumber = last + 1;
    }

    private int LastNumber(IEnumerable<string> folders)
    {
        var parts = template.Split("{number}");
        var matcher = new Regex("^" + Regex.Escape(parts[0]) + "([0-9]{1,9})" + Regex.Escape(parts[1]) + "$",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100));
        var last = 0;
        foreach (var folder in folders.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            foreach (var path in Directory.EnumerateFiles(folder))
            {
                var match = matcher.Match(Path.GetFileNameWithoutExtension(path));
                if (match.Success && int.TryParse(match.Groups[1].Value, out var value)) last = Math.Max(last, value);
            }
        }
        return last;
    }

    public string Next(string originalName)
    {
        if (number > 999999999) throw new ArgumentException("A numeração excedeu o limite permitido.");
        var name = template.Replace("{number}", number.ToString("D" + digits, CultureInfo.InvariantCulture))
            + Path.GetExtension(originalName);
        number++;
        AssetFileService.ValidateName(name);
        return name;
    }
}
