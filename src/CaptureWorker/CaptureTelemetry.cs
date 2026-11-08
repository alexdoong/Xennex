using System;
using System.Text.Json;

namespace Xennex.CaptureWorker;

internal readonly record struct FrameStageSample(int SourceWidth, int SourceHeight, int OutputWidth, int OutputHeight,
    string ScalePath, long MappedBytes, long SourceBytes, double MapMs, double BeforeJpegMs, double JpegMs, double TotalMs);

// One bounded window; no paths, titles, pixels, tokens or network addresses are recorded.
internal sealed class CaptureTelemetry
{
    private readonly FrameStageSample[] samples = new FrameStageSample[256];
    private int count;
    private double? start;
    internal string Snapshot { get; private set; } = "";
    internal bool Add(FrameStageSample sample, double nowMs)
    {
        if (count > 0 && (samples[0].SourceWidth != sample.SourceWidth || samples[0].SourceHeight != sample.SourceHeight ||
            samples[0].OutputWidth != sample.OutputWidth || samples[0].OutputHeight != sample.OutputHeight || samples[0].ScalePath != sample.ScalePath))
        { count = 0; start = null; }
        start ??= nowMs;
        samples[count++] = sample;
        if (count < samples.Length && nowMs - start.Value < 2000) return false;
        double map = 0, before = 0, jpeg = 0, total = 0;
        var timings = new double[count];
        for (int i = 0; i < count; i++)
        { map += samples[i].MapMs; before += samples[i].BeforeJpegMs; jpeg += samples[i].JpegMs; total += timings[i] = samples[i].TotalMs; }
        Array.Sort(timings);
        double windowMs = Math.Max(1, nowMs - start.Value);
        Snapshot = JsonSerializer.Serialize(new
        {
            type = "capture-metrics", version = 1, sourceWidth = sample.SourceWidth, sourceHeight = sample.SourceHeight,
            outputWidth = sample.OutputWidth, outputHeight = sample.OutputHeight, scalePath = sample.ScalePath,
            mappedBytes = sample.MappedBytes, sourceBytes = sample.SourceBytes,
            samples = count, windowMs, processedFps = Math.Max(0, count - 1) * 1000.0 / windowMs,
            mapMs = map / count, beforeJpegMs = before / count, jpegMs = jpeg / count,
            totalMs = total / count, p95Ms = timings[(int)Math.Ceiling(count * .95) - 1],
        });
        count = 0; start = null;
        return true;
    }
}
