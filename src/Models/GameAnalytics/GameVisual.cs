using System.Collections.Generic;

namespace Xennex.Models.GameAnalytics
{
    public sealed class GameVisual
    {
        public string Cover { get; set; } = "";
        public List<GameCharacter> Characters { get; set; } = new();
        public List<StrategyBoard> Boards { get; set; } = new();
    }
    public sealed class GameCharacter
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string Role { get; set; } = "";
        public string Notes { get; set; } = "";
        public string Image { get; set; } = "";
        public double Focus { get; set; } = 50;
        public string Color { get; set; } = "#a78bfa";
    }
    public sealed class StrategyBoard
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string Goal { get; set; } = "";
        public List<StrategyCard> Cards { get; set; } = new();
        public List<StrategyLink> Links { get; set; } = new();
    }
    public sealed class StrategyCard
    {
        public string Id { get; set; } = "";
        public string CharacterId { get; set; } = "";
        public string Title { get; set; } = "";
        public string Notes { get; set; } = "";
        public string Color { get; set; } = "#a78bfa";
        public double X { get; set; }
        public double Y { get; set; }
    }
    public sealed class StrategyLink
    {
        public string From { get; set; } = "";
        public string To { get; set; } = "";
    }
}
