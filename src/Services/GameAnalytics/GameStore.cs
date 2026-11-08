using System;
using System.IO;
using System.Text;
using System.Text.Json;
using Xennex.Models.GameAnalytics;

namespace Xennex.Services.GameAnalytics
{
    /// <summary>One atomic, revision-checked document per game. Personal data only.</summary>
    public sealed class GameStore
    {
        public const int MaxBytes = 32_000_000;
        public static readonly JsonSerializerOptions Json = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true
        };
        private readonly string directory;
        private readonly object sync = new();
        public GameStore(string directory) { this.directory = directory; }
        public string[] Files() => Directory.Exists(directory)
            ? Directory.GetFiles(directory, "*.json") : Array.Empty<string>();
        public GameDocument ReadFile(string path)
        {
            if (new FileInfo(path).Length > MaxBytes)
                throw new InvalidDataException("Arquivo de jogo acima de 32 MB.");
            return Parse(File.ReadAllText(path));
        }
        public static GameDocument Parse(string json)
        {
            if (json == null || Encoding.UTF8.GetByteCount(json) > MaxBytes)
                throw new InvalidDataException("Arquivo de jogo acima de 32 MB.");
            var document = JsonSerializer.Deserialize<GameDocument>(json, Json);
            // Read-only migration; the original is backed up on the next explicit save.
            GameMigration.Upgrade(document);
            GameValidation.Validate(document);
            return document;
        }
        public GameDocument Save(GameDocument document)
        {
            lock (sync)
            {
                GameValidation.Validate(document);
                Directory.CreateDirectory(directory);
                var path = Path.Combine(directory, document.Id.ToLowerInvariant() + ".json");
                var previous = File.Exists(path) ? ReadFile(path) : null;
                if (document.Revision != (previous?.Revision ?? 0))
                    throw new InvalidDataException("Este jogo mudou. Recarregue antes de salvar novamente.");
                document.Revision++;
                var json = JsonSerializer.Serialize(document, Json);
                if (Encoding.UTF8.GetByteCount(json) > MaxBytes)
                    throw new InvalidDataException("Limite de 32 MB por jogo atingido. Exporte seus registros.");
                var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
                try
                {
                    using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    {
                        var bytes = Encoding.UTF8.GetBytes(json);
                        stream.Write(bytes);
                        stream.Flush(true);
                    }
                    if (previous == null) File.Move(temporary, path);
                    else File.Replace(temporary, path, path + ".bak");
                }
                finally
                {
                    if (File.Exists(temporary)) File.Delete(temporary);
                }
                return document;
            }
        }
    }
}
