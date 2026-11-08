using System;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

/// <summary>Sampled global deltas can include other apps; use only to raise future reservations.</summary>
internal sealed class JobMemoryObservation
{
    private readonly ResourceSnapshot baseline;
    public double Ram { get; private set; }
    public double Vram { get; private set; }
    public JobMemoryObservation(ResourceSnapshot baseline) { this.baseline = baseline; }
    public void Sample(ResourceSnapshot snapshot)
    {
        if (snapshot.RamUsedGb.HasValue && baseline.RamUsedGb.HasValue) Ram = Math.Max(Ram, snapshot.RamUsedGb.Value - baseline.RamUsedGb.Value);
        if (snapshot.VramUsedGb.HasValue && baseline.VramUsedGb.HasValue) Vram = Math.Max(Vram, snapshot.VramUsedGb.Value - baseline.VramUsedGb.Value);
    }
}
