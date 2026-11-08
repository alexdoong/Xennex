using System;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

/// <summary>Admission policy, not an OS memory cap. Caller serializes reservations.</summary>
public static class ResourcePolicy
{
    public static string Check(ResourceSnapshot snapshot, AiSettings settings, bool starting)
    {
        if (snapshot == null || DateTimeOffset.UtcNow - snapshot.CapturedAt > TimeSpan.FromSeconds(10))
            return "Aguardando medição atual de memória.";
        var ram = CheckMemory("RAM", snapshot.RamTotalGb, snapshot.RamUsedGb,
            settings.MemoryLimitPercent, starting ? settings.AdditionalRamGb : 0);
        if (ram != "") return ram;
        if (!settings.UseGpu) return "";
        return CheckMemory("VRAM", snapshot.VramTotalGb, snapshot.VramUsedGb,
            settings.MemoryLimitPercent, starting ? settings.AdditionalVramGb : 0);
    }

    private static string CheckMemory(string label, double? total, double? used, int percent, double extra)
    {
        if (!total.HasValue || !used.HasValue || !double.IsFinite(total.Value) ||
            !double.IsFinite(used.Value) || total <= 0 || used < 0)
            return $"Aguardando telemetria de {label}.";
        double budget = total.Value * percent / 100.0;
        if (extra > budget) return $"A reserva de {label} não cabe no orçamento. Reduza o modelo/contexto ou a reserva após medir.";
        if (used.Value + extra > budget)
            return $"Aguardando {label}: uso {used:0.0} + reserva {extra:0.0} GiB ultrapassa o limite de {budget:0.0} GiB.";
        return "";
    }
}
