using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Xennex.Services.Updates
{
    public sealed record ApprovedUpdate(string Version, string Url, string Name, string Sha256, long Size);
    public static class UpdatePolicy
    {
        public const string LatestReleaseUrl = "https://api.github.com/repos/alexdoong/Xennex/releases/latest";
        public const long MaximumPackageBytes = 1024L * 1024 * 1024;
        public static bool IsReleaseUrl(string value) => Uri.TryCreate(value, UriKind.Absolute, out var uri) &&
            uri.Scheme == "https" && uri.Host == "github.com" && uri.IsDefaultPort && uri.UserInfo == "" &&
            uri.Query == "" && uri.Fragment == "" &&
            Regex.IsMatch(uri.AbsolutePath, @"^/alexdoong/Xennex/releases/download/v\d+\.\d+\.\d+/Xennex-v\d+\.\d+\.\d+-win64\.zip$");
        public static bool IsDownloadRedirect(Uri uri) => uri.Scheme == "https" && uri.IsDefaultPort && uri.UserInfo == "" &&
            (uri.Host == "github.com" || uri.Host == "release-assets.githubusercontent.com" || uri.Host == "objects.githubusercontent.com");
        public static ApprovedUpdate ReadApprovedAsset(JsonElement release, string currentVersion)
        {
            if (release.GetProperty("draft").GetBoolean() || release.GetProperty("prerelease").GetBoolean())
                throw new InvalidDataException("Release de desenvolvimento não pode ser instalada automaticamente.");
            string tag = release.GetProperty("tag_name").GetString() ?? "";
            if (!Regex.IsMatch(tag, @"^v\d+\.\d+\.\d+$") || !Version.TryParse(tag[1..], out var latest) ||
                !Version.TryParse(currentVersion.TrimStart('v'), out var current) || latest <= current)
                throw new InvalidDataException("A release não é uma versão estável mais recente.");
            string name = $"Xennex-{tag}-win64.zip";
            var assets = release.GetProperty("assets").EnumerateArray().Where(item => item.GetProperty("name").GetString() == name).ToArray();
            if (assets.Length != 1) throw new InvalidDataException("Pacote portátil esperado não encontrado na release.");
            var asset = assets[0];
            string url = asset.GetProperty("browser_download_url").GetString() ?? "";
            if (!IsReleaseUrl(url) || url != $"https://github.com/alexdoong/Xennex/releases/download/{tag}/{name}")
                throw new InvalidDataException("Endereço da atualização não pertence à release esperada.");
            string digest = asset.TryGetProperty("digest", out var field) ? field.GetString() ?? "" : "";
            if (!Regex.IsMatch(digest, "^sha256:[a-fA-F0-9]{64}$"))
                throw new InvalidDataException("GitHub não forneceu SHA-256 verificável para este pacote. Use a instalação manual.");
            long size = asset.GetProperty("size").GetInt64();
            if (size <= 0 || size > MaximumPackageBytes) throw new InvalidDataException("Tamanho de atualização inválido.");
            return new ApprovedUpdate(tag, url, name, digest[7..].ToUpperInvariant(), size);
        }
        public static async Task DownloadVerified(Stream input, Stream output, ApprovedUpdate asset, CancellationToken token)
        {
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            byte[] buffer = new byte[81920]; long total = 0; int count;
            while ((count = await input.ReadAsync(buffer, token)) != 0)
            {
                total += count;
                if (total > asset.Size || total > MaximumPackageBytes) throw new InvalidDataException("Download maior que o pacote declarado.");
                hash.AppendData(buffer, 0, count); await output.WriteAsync(buffer.AsMemory(0, count), token);
            }
            if (total != asset.Size || !Convert.ToHexString(hash.GetHashAndReset()).Equals(asset.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("SHA-256 ou tamanho da atualização diverge da release. Instalação cancelada.");
        }
    }
}
