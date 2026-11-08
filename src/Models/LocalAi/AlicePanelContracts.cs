namespace Xennex.Models.LocalAi;

public sealed class AlicePanelSettings
{
    public string Python { get; set; } = "";
    public string Checkpoint { get; set; } = "";
    public string Endpoint { get; set; } = "http://127.0.0.1:11436";
    public string Model { get; set; } = "qwen3.5:0.8b-q8_0";
    public string DialogueModel { get; set; } = "";
    public string PerceptionPython { get; set; } = "";
    public string PerceptionModels { get; set; } = "";
    public string MirageModels { get; set; } = "";
    public int Seconds { get; set; }
    public double RamFraction { get; set; } = .75;
    public string Attention { get; set; } = "full";
    public string MemoryRecall { get; set; } = "preserve";
}
