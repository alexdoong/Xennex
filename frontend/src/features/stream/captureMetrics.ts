export interface CaptureMetrics {
  sourceWidth: number; sourceHeight: number; outputWidth: number; outputHeight: number;
  scalePath: 'gpu' | 'cpu' | 'none'; mappedBytes: number; sourceBytes: number;
  samples: number; windowMs: number; processedFps: number;
  mapMs: number; beforeJpegMs: number; jpegMs: number; totalMs: number; p95Ms: number;
}
export interface CapturePipeline {
  worker: CaptureMetrics; receivedAt: number; decodeMs?: number; drawMs?: number;
  decoder?: 'webcodecs' | 'bitmap'; output?: 'generator' | 'worker-generator' | 'canvas'; submitMs?: number;
  decodeP95Ms?: number; queueMs?: number; ageP95Ms?: number;
  receivedFrames?: number; replacedFrames?: number;
}

// This is authenticated local telemetry, not room signaling. Still bound every received value.
export function parseCaptureMetrics(text: string): CaptureMetrics | undefined {
  if (text.length > 4096) return;
  try {
    const data: unknown = JSON.parse(text);
    if (!data || typeof data !== 'object') return;
    const v = data as Record<string, unknown>;
    if (v.type !== 'capture-metrics' || v.version !== 1 || !['gpu', 'cpu', 'none'].includes(String(v.scalePath))) return;
    const range = (key: string, min: number, max: number) => typeof v[key] === 'number' && Number.isFinite(v[key]) && v[key] >= min && v[key] <= max;
    for (const key of ['sourceWidth', 'sourceHeight', 'outputWidth', 'outputHeight']) if (!range(key, 2, 16384) || !Number.isInteger(v[key])) return;
    for (const key of ['sourceBytes', 'mappedBytes']) if (!range(key, 8, 2 ** 32)) return;
    if (!range('samples', 1, 256) || !Number.isInteger(v.samples) || !range('windowMs', 1, 60000) || !range('processedFps', 0, 1000)) return;
    for (const key of ['mapMs', 'beforeJpegMs', 'jpegMs', 'totalMs', 'p95Ms']) if (!range(key, 0, 60000)) return;
    // Explicit fields ensure arbitrary worker properties never propagate to UI state.
    return {
      sourceWidth: v.sourceWidth as number, sourceHeight: v.sourceHeight as number,
      outputWidth: v.outputWidth as number, outputHeight: v.outputHeight as number,
      scalePath: v.scalePath as CaptureMetrics['scalePath'], mappedBytes: v.mappedBytes as number, sourceBytes: v.sourceBytes as number,
      samples: v.samples as number, windowMs: v.windowMs as number, processedFps: v.processedFps as number,
      mapMs: v.mapMs as number, beforeJpegMs: v.beforeJpegMs as number, jpegMs: v.jpegMs as number, totalMs: v.totalMs as number, p95Ms: v.p95Ms as number,
    };
  } catch { return; }
}

// Windowed frontend averages. Submission is not GPU completion or end-to-end latency.
export class CaptureFrameTimings {
  private count = 0; private decode = 0; private draw = 0;
  private queue = 0; private received = 0; private replaced = 0;
  private decodes: number[] = []; private ages: number[] = [];
  arrived() { this.received++; }
  dropped() { this.replaced++; }
  add(decodeMs: number, drawMs: number, queueMs = 0) {
    if (this.count >= 256) return;
    this.count++; this.decode += decodeMs; this.draw += drawMs; this.queue += queueMs;
    this.decodes.push(decodeMs); this.ages.push(queueMs + decodeMs + drawMs);
  }
  take(output: 'canvas' | 'generator' = 'canvas'): Partial<CapturePipeline> {
    const percentile = (values: number[]) => values.sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1];
    const result = this.count ? { decodeMs: this.decode / this.count, ...(output === 'generator' ? { submitMs: this.draw / this.count } : { drawMs: this.draw / this.count }),
      decodeP95Ms: percentile(this.decodes), queueMs: this.queue / this.count, ageP95Ms: percentile(this.ages),
      receivedFrames: this.received, replacedFrames: this.replaced } : {};
    this.count = this.decode = this.draw = this.queue = this.received = this.replaced = 0;
    this.decodes = []; this.ages = [];
    return result;
  }
}
