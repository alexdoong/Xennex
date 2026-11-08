using System.Collections.Generic;

namespace Xennex.Models.GameAnalytics
{
    public sealed class GameDefinition
    {
        public string Category { get; set; } = "Personalizado";
        public bool HasEntities { get; set; } = true;
        public string EntityLabel { get; set; } = "Personagens";
        public bool HasRanked { get; set; }
        public List<NamedGameDefinition> Skills { get; set; } = new();
        public List<NamedGameDefinition> Actions { get; set; } = new();
        public List<NamedGameDefinition> ContextFields { get; set; } = new();
        public List<MetricDefinition> Metrics { get; set; } = new();
    }
    public class NamedGameDefinition
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string Description { get; set; } = "";
        public bool Archived { get; set; }
    }
    public sealed class MetricDefinition : NamedGameDefinition
    {
        public string Unit { get; set; } = "";
        public string Direction { get; set; } = "neutral";
        public string SkillId { get; set; } = "";
    }
    public sealed class SessionContext
    {
        public string DefinitionId { get; set; } = "";
        public string Name { get; set; } = "";
        public string Value { get; set; } = "";
    }
    public sealed class SessionEvent
    {
        public string ActionId { get; set; } = "";
        public string ActionName { get; set; } = "";
        public string Actor { get; set; } = "";
        public double AtSeconds { get; set; }
        public string MetricId { get; set; } = "";
        public string MetricName { get; set; } = "";
        public double? Value { get; set; }
        public string Unit { get; set; } = "";
        public string Notes { get; set; } = "";
    }
}
