export interface RtpHealthCounters {
  packetsReceived?: number; packetsLost?: number; framesDropped?: number; freezeCount?: number;
  nackCount?: number; pliCount?: number; totalEncodeTime?: number; totalDecodeTime?: number;
  jitterBufferDelay?: number; jitterBufferEmittedCount?: number;
}
export interface RtpHealth {
  lossPercent?: number; droppedFrames?: number; freezes?: number; nacks?: number; plis?: number;
  encodeMs?: number; decodeMs?: number; jitterBufferMs?: number;
}
export interface RtpSample { timestamp: number; bytes?: number; frames?: number; receivedFrames?: number; health?: RtpHealthCounters }
export interface VideoReading { width?: number; height?: number; fps?: number; arrivalFps?: number; mbps?: number; health?: RtpHealth; activity?: 'focused' | 'unfocused' | 'hidden' }
export interface RtpReport extends RtpHealthCounters {
  timestamp: number; bytesSent?: number; bytesReceived?: number; framesEncoded?: number;
  framesDecoded?: number; framesReceived?: number; framesPerSecond?: number; frameWidth?: number; frameHeight?: number;
}
const counter = (value: number | undefined) => value !== undefined && Number.isFinite(value) && value >= 0 ? value : undefined;
const HEALTH_FIELDS = ['packetsReceived', 'packetsLost', 'framesDropped', 'freezeCount', 'nackCount', 'pliCount',
  'totalEncodeTime', 'totalDecodeTime', 'jitterBufferDelay', 'jitterBufferEmittedCount'] as const;
/** Missing counters are unknown, not a frozen 0 FPS stream. Counter resets start a new baseline. */
export function sampleRtp(report: RtpReport, last?: RtpSample): { sample: RtpSample; reading: VideoReading } {
  const bytes = counter(report.bytesSent ?? report.bytesReceived);
  const frames = counter(report.framesEncoded ?? report.framesDecoded);
  const receivedFrames = counter(report.framesReceived);
  const health: RtpHealthCounters = {};
  for (const key of HEALTH_FIELDS) health[key] = counter(report[key]);
  const elapsed = last ? report.timestamp - last.timestamp : 0;
  const fps = counter(report.framesPerSecond);
  const reading: VideoReading = { width: counter(report.frameWidth), height: counter(report.frameHeight), fps: fps && fps > 0 ? fps : undefined };
  if (last && elapsed > 0 && elapsed <= 10000) {
    if (bytes !== undefined && last.bytes !== undefined && bytes >= last.bytes) reading.mbps = (bytes - last.bytes) * 8 / elapsed / 1000;
    if (frames !== undefined && last.frames !== undefined && frames >= last.frames) reading.fps = (frames - last.frames) * 1000 / elapsed;
    if (receivedFrames !== undefined && last.receivedFrames !== undefined && receivedFrames >= last.receivedFrames) reading.arrivalFps = (receivedFrames - last.receivedFrames) * 1000 / elapsed;
    const delta = (key: keyof RtpHealthCounters) => {
      const current = health[key], before = last.health?.[key];
      return current !== undefined && before !== undefined && current >= before ? current - before : undefined;
    };
    const average = (seconds: number | undefined, count: number | undefined) => seconds !== undefined && count !== undefined && count > 0 ? seconds * 1000 / count : undefined;
    const frameCount = frames !== undefined && last.frames !== undefined && frames >= last.frames ? frames - last.frames : undefined;
    const packets = delta('packetsReceived'), lost = delta('packetsLost');
    reading.health = {
      lossPercent: packets !== undefined && lost !== undefined && packets + lost > 0 ? lost / (packets + lost) * 100 : undefined,
      droppedFrames: delta('framesDropped'), freezes: delta('freezeCount'), nacks: delta('nackCount'), plis: delta('pliCount'),
      encodeMs: average(delta('totalEncodeTime'), frameCount), decodeMs: average(delta('totalDecodeTime'), frameCount),
      jitterBufferMs: average(delta('jitterBufferDelay'), delta('jitterBufferEmittedCount')),
    };
  }
  return { sample: { timestamp: report.timestamp, bytes, frames, receivedFrames, health }, reading };
}
