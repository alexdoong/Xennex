using System;
using System.Collections.Generic;

namespace Xennex.Models.LocalAi;

public sealed class OllamaModel
{
    public string Name { get; set; } = "";
    public string Digest { get; set; } = "";
    public double DiskGb { get; set; }
    public double LoadedGb { get; set; }
    public double LoadedVramGb { get; set; }
    public int LoadedContext { get; set; }
    public bool Loaded { get; set; }
    public bool PlacementKnown { get; set; }
}
public sealed class OllamaSnapshot
{
    public string Endpoint { get; set; } = "";
    public DateTimeOffset CapturedAt { get; set; } = DateTimeOffset.UtcNow;
    public List<OllamaModel> Models { get; set; } = new();
}
public sealed class OllamaModelInfo
{
    public bool LocalCompletion { get; set; }
    public double? CacheBytesPerToken { get; set; }
}
public sealed class ResourceDemand
{
    public double RamGb { get; set; }
    public double VramGb { get; set; }
    public string Source { get; set; } = "manual";
    public string Detail { get; set; } = "Reserva manual";
    public string MeasurementKey { get; set; } = "";
    public bool AlreadyLoaded { get; set; }
}
public sealed class ResourceMeasurement
{
    public string Key { get; set; } = "";
    public int Samples { get; set; }
    public double AdditionalRamGb { get; set; }
    public double AdditionalVramGb { get; set; }
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}
