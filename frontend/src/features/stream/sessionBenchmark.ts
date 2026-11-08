import { PROTOCOL } from './protocol';
import { STREAM_BUILD } from './entryDiagnostics';
import type { VideoReading } from './streamStats';

const fields = ['fps', 'arrivalFps', 'mbps', 'encodeMs', 'decodeMs', 'jitterBufferMs', 'lossPercent'] as const;
type Field = typeof fields[number];
interface TrackSamples { direction: 'incoming' | 'outgoing'; samples: number; width?: number; height?: number; codec?: string; values: Record<Field, number[]>; activity: Record<'focused' | 'unfocused' | 'hidden' | 'unknown', number>; drops?: number; freezes?: number }
export interface Distribution { samples: number; mean: number; p50: number; p95: number; min: number; max: number }
const valid = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e7;
export function distribution(values: number[]): Distribution | null {
  const sorted = values.filter(valid).sort((a, b) => a - b);
  if (!sorted.length) return null;
  return { samples: sorted.length, mean: sorted.reduce((a, b) => a + b, 0) / sorted.length,
    p50: sorted[Math.ceil(sorted.length * .5) - 1], p95: sorted[Math.ceil(sorted.length * .95) - 1], min: sorted[0], max: sorted[sorted.length - 1] };
}

/** Voluntary local RTP benchmark. Identity keys never leave this object. No SDP, names, IPs or frames. */
export class SessionBenchmark {
  private started: number;
  private ended?: number;
  private durationMs: number;
  private tracks = new Map<object, TrackSamples>();
  private now: () => number;
  constructor(durationSeconds: 60 | 900, now = Date.now) {
    this.now = now; this.started = now(); this.durationMs = durationSeconds === 900 ? 900000 : 60000;
  }
  get active() { return this.ended === undefined && this.now() - this.started < this.durationMs; }
  get secondsRemaining() { return this.active ? Math.max(0, Math.ceil((this.durationMs - (this.now() - this.started)) / 1000)) : 0; }
  stop() { this.ended ??= Math.min(this.now(), this.started + this.durationMs); }
  record(key: object, direction: 'incoming' | 'outgoing', reading: VideoReading, codec?: string) {
    if (!this.active) return;
    let track = this.tracks.get(key);
    if (!track) {
      if (this.tracks.size >= 256) return;
      track = { direction, samples: 0, activity: { focused: 0, unfocused: 0, hidden: 0, unknown: 0 }, values: { fps: [], arrivalFps: [], mbps: [], encodeMs: [], decodeMs: [], jitterBufferMs: [], lossPercent: [] } };
      this.tracks.set(key, track);
    }
    track.samples++;
    const activity = reading.activity === 'focused' || reading.activity === 'unfocused' || reading.activity === 'hidden' ? reading.activity : 'unknown';
    track.activity[activity]++;
    if (valid(reading.width)) track.width = reading.width;
    if (valid(reading.height)) track.height = reading.height;
    if (codec && /^video\/(H264|H265|VP8|VP9|AV1)$/i.test(codec)) track.codec = codec;
    for (const field of fields) {
      const value = field === 'fps' || field === 'arrivalFps' || field === 'mbps' ? reading[field] : reading.health?.[field];
      if (valid(value)) { track.values[field].push(value); if (track.values[field].length > 512) track.values[field].shift(); }
    }
    if (valid(reading.health?.droppedFrames)) track.drops = (track.drops ?? 0) + reading.health.droppedFrames;
    if (valid(reading.health?.freezes)) track.freezes = (track.freezes ?? 0) + reading.health.freezes;
  }
  report() {
    return { schema: 'xennex-rtp-benchmark-v1', build: STREAM_BUILD, protocol: PROTOCOL,
      requestedSeconds: this.durationMs / 1000,
      measuredSeconds: Math.max(0, (Math.min(this.ended ?? this.now(), this.started + this.durationMs) - this.started) / 1000),
      active: this.active,
      scope: 'RTP measured on this endpoint; fps is encoded/decoded rate, arrivalFps is frames received before decoding. Visibility counts identify focused/unfocused/hidden samples. Not raw capture, CPU/GPU usage or synchronized end-to-end latency. Up to 256 tracks and last 512 valid samples per field. No hardware acceleration inferred.',
      tracks: [...this.tracks.values()].map((track, index) => ({ number: index + 1, direction: track.direction,
        samples: track.samples, lastWidth: track.width ?? null, lastHeight: track.height ?? null, lastCodec: track.codec ?? null,
        activitySamples: { ...track.activity },
        measuredDrops: track.drops ?? null, measuredFreezes: track.freezes ?? null,
        metrics: Object.fromEntries(fields.map(field => [field, distribution(track.values[field])])) })),
    };
  }
}
