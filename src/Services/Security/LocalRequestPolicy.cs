#nullable enable
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace Xennex.Services.Security
{
    public static class LocalRequestPolicy
    {
        public static string CaptureToken { get; } = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        public static bool IsAppDocument(string? value) =>
            Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme == "https" &&
            uri.Host == "appassets" && uri.IsDefaultPort && uri.UserInfo == "" && uri.AbsolutePath == "/index.html";
        public static bool IsCaptureAllowed(string? origin, string? token, string? expected) =>
            origin == "https://appassets" && expected?.Length == 64 && token?.Length == 64 &&
            CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(token), Encoding.ASCII.GetBytes(expected));

        // Inspect the raw request target: Uri normalizes some dot segments before AbsolutePath is read.
        public static string? ResolvePublicFile(string root, string? rawTarget)
        {
            if (string.IsNullOrEmpty(rawTarget) || !rawTarget.StartsWith("/") || rawTarget.StartsWith("//")) return null;
            try
            {
                string path = Uri.UnescapeDataString(rawTarget.Split('?')[0]);
                if (path.Contains('%') || path.Contains('\\') || path.Contains(':') || path.Contains('\0')) return null;
                string relative = path.TrimStart('/');
                if (relative.Length == 0) relative = "watch.html";
                foreach (string segment in relative.Split('/'))
                    if (segment == "." || segment == ".." || segment.EndsWith(' ') || segment.EndsWith('.')) return null;
                string directory = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                string candidate = Path.GetFullPath(Path.Combine(directory, relative.Replace('/', Path.DirectorySeparatorChar)));
                if (!candidate.StartsWith(directory, StringComparison.OrdinalIgnoreCase)) return null;
                // A junction/symlink below wwwroot must not expose another directory.
                for (string? current = candidate; current != null && current.StartsWith(directory, StringComparison.OrdinalIgnoreCase); current = Path.GetDirectoryName(current))
                    if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) return null;
                return candidate;
            }
            catch (Exception error) when (error is ArgumentException || error is IOException || error is UnauthorizedAccessException || error is NotSupportedException)
            { return null; }
        }
    }
}
