using System;
using System.Linq;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Xennex.Models.GameAnalytics;

namespace Xennex.Services.GameAnalytics
{
    public static class GameMigration
    {
        public static void Upgrade(GameDocument game)
        {
            if (game == null || game.SchemaVersion < 1 || game.SchemaVersion > 2) return;
            game.Definition ??= new();
            if (game.Definition.Metrics == null) throw new InvalidDataException("Catálogo de métricas inválido.");
            // Stable IDs across reads: loading alone must not change identities or disk contents.
            foreach (var metric in game.Sessions?.Where(s => s != null).SelectMany(s => s.Metrics ?? new()) ?? Enumerable.Empty<GameMetric>())
            {
                if (metric == null || metric.Name == null || metric.Unit == null) continue;
                var key = metric.Name.Trim().ToUpperInvariant() + "\n" + metric.Unit.Trim().ToUpperInvariant();
                var id = new Guid(SHA256.HashData(Encoding.UTF8.GetBytes("legacy-metric\n" + key)).Take(16).ToArray()).ToString();
                if (!game.Definition.Metrics.Any(m => m?.Id == id) && game.Definition.Metrics.Count >= 100) { metric.DefinitionId = ""; continue; }
                if (!game.Definition.Metrics.Any(m => m?.Id == id))
                    game.Definition.Metrics.Add(new MetricDefinition { Id = id, Name = metric.Name, Unit = metric.Unit });
                metric.DefinitionId = id;
            }
            game.SchemaVersion = 3;
        }
    }
}
