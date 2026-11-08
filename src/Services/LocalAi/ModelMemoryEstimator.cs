using System;
using System.Collections.Generic;
using System.Linq;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public static class ModelMemoryEstimator
{
    public static ResourceDemand Manual(AiSettings settings) => new() { RamGb = settings.AdditionalRamGb, VramGb = settings.UseGpu ? settings.AdditionalVramGb : 0 };
    public static ResourceDemand Estimate(AiSettings settings, OllamaModel model, OllamaModelInfo info, IEnumerable<ResourceMeasurement> measurements)
    {
        if (model == null || model.DiskGb <= 0 || !double.IsFinite(model.DiskGb) || !info.LocalCompletion)
            throw new InvalidOperationException("Escolha um modelo de conversa baixado localmente. Modelos remotos não são admitidos.");
        bool resident = model.Loaded && model.PlacementKnown && model.LoadedContext == settings.ContextTokens &&
            (settings.UseGpu ? model.LoadedVramGb > .01 : model.LoadedVramGb <= .01);
        double cache = info.CacheBytesPerToken.HasValue ? info.CacheBytesPerToken.Value * settings.ContextTokens / 1073741824.0 : settings.ContextTokens / 4096.0 * 2;
        double cold = model.DiskGb * 1.15 + cache + 1;
        var demand = new ResourceDemand
        {
            RamGb = resident ? 1 : cold,
            VramGb = settings.UseGpu ? (resident ? 1 : cold) : 0,
            Source = "estimate", AlreadyLoaded = resident,
            MeasurementKey = $"{LocalModelClient.Endpoint(settings.Endpoint)}|{model.Digest}|{model.Name}|{settings.ContextTokens}|{settings.UseGpu}|{resident}",
            Detail = resident ? "Modelo já residente no contexto solicitado. Reserva adicional para execução; pesos não são contados novamente." : "Estimativa conservadora de carregamento, cache de contexto e buffers. Não representa uma garantia de pico."
        };
        var observed = measurements.FirstOrDefault(m => m.Key == demand.MeasurementKey);
        if (observed != null)
        {
            demand.RamGb = Math.Max(demand.RamGb, observed.AdditionalRamGb * 1.15 + .25);
            if (settings.UseGpu) demand.VramGb = Math.Max(demand.VramGb, observed.AdditionalVramGb * 1.15 + .25);
            demand.Source = "observed";
            demand.Detail += $" Considera também {observed.Samples} execução(ões) observada(s). Variações de outros apps podem aumentar a estimativa.";
        }
        return demand;
    }
    public static void Observe(List<ResourceMeasurement> measurements, ResourceDemand demand, double ram, double vram)
    {
        if (demand == null || demand.MeasurementKey.Length == 0 || !double.IsFinite(ram) || !double.IsFinite(vram)) return;
        var observation = measurements.FirstOrDefault(m => m.Key == demand.MeasurementKey);
        if (observation == null)
        {
            observation = new ResourceMeasurement { Key = demand.MeasurementKey }; measurements.Add(observation);
        }
        observation.AdditionalRamGb = Math.Max(observation.AdditionalRamGb, Math.Max(0, ram));
        observation.AdditionalVramGb = Math.Max(observation.AdditionalVramGb, Math.Max(0, vram));
        observation.Samples = Math.Min(1000000, observation.Samples + 1); observation.UpdatedAt = DateTimeOffset.UtcNow;
        while (measurements.Count > 64) measurements.Remove(measurements.OrderBy(m => m.UpdatedAt).First());
    }
}
