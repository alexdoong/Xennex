using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Xennex.Models.GameAnalytics
{
    public sealed class GameDocument
    {
        [JsonRequired]
        public int SchemaVersion { get; set; } = 3;
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public int Revision { get; set; }
        public GameVisual Visual { get; set; } = new();
        public GameDefinition Definition { get; set; } = new();
        [JsonRequired]
        public List<GameSession> Sessions { get; set; } = new();
    }
    public sealed class GameSession
    {
        public string Id { get; set; } = "";
        public string Title { get; set; } = "";
        public DateTimeOffset OccurredAt { get; set; }
        public DateTimeOffset CreatedAt { get; set; }
        public DateTimeOffset UpdatedAt { get; set; }
        public string Patch { get; set; } = "";
        public string Context { get; set; } = "";
        public string Notes { get; set; } = "";
        public string Source { get; set; } = "manual";
        public List<SessionContext> ContextValues { get; set; } = new();
        public List<SessionEvent> Events { get; set; } = new();
        public List<GameMetric> Metrics { get; set; } = new();
    }
    public sealed class GameMetric
    {
        public string DefinitionId { get; set; } = "";
        public string Name { get; set; } = "";
        [JsonRequired]
        public double Value { get; set; }
        public string Unit { get; set; } = "";
    }
}
