import type { Quality } from './quality';

export const CODECS = ['h264', 'vp8', 'vp9', 'av1'] as const;
export type VideoCodec = typeof CODECS[number];
export type CodecMode = 'auto' | 'compatibility' | VideoCodec;
export const CODEC_LABELS: Record<VideoCodec, string> = { h264: 'H.264', vp8: 'VP8', vp9: 'VP9', av1: 'AV1' };
export interface CodecEvidence { codec: VideoCodec; advertised: boolean; supported?: boolean; smooth?: boolean; powerEfficient?: boolean }
export interface CodecReport { direction: 'encode' | 'decode'; codecs: CodecEvidence[]; width: number; height: number; fps: number }
const cache = new Map<string, { time: number; report?: CodecReport; pending?: Promise<CodecReport> }>();
let pendingProfiles = 0;
const types: Record<VideoCodec, string> = { h264: 'video/H264', vp8: 'video/VP8', vp9: 'video/VP9', av1: 'video/AV1' };
const sizes = { '720p': [1280, 720], '1080p': [1920, 1080], '1440p': [2560, 1440], '2160p': [3840, 2160], source: [1920, 1080] } as const;
const fallbackQuality: Quality = { resolution: '1080p', fps: 30, preference: 'motion', uploadMbps: 12 };
export const codecMode = (value: unknown): CodecMode => typeof value === 'string' && ['auto', 'compatibility', ...CODECS].includes(value) ? value as CodecMode : 'auto';
export function captureSupport() {
  return { watch: typeof RTCPeerConnection === 'function',
    screen: typeof navigator !== 'undefined' && typeof navigator.mediaDevices?.getDisplayMedia === 'function',
    camera: typeof navigator !== 'undefined' && typeof navigator.mediaDevices?.getUserMedia === 'function' };
}
export function qualityHint(value: unknown): Quality {
  if (!value || typeof value !== 'object') return fallbackQuality;
  const v = value as Record<string, unknown>;
  return { ...fallbackQuality,
    resolution: typeof v.resolution === 'string' && Object.hasOwn(sizes, v.resolution) ? v.resolution as Quality['resolution'] : '1080p',
    fps: typeof v.fps === 'number' && Number.isFinite(v.fps) ? Math.max(1, Math.min(120, Math.round(v.fps) || 120)) : 30,
    uploadMbps: typeof v.uploadMbps === 'number' && Number.isFinite(v.uploadMbps) ? Math.max(1, Math.min(1000, v.uploadMbps)) : 12 };
}
function profile(quality: Quality, direction: CodecReport['direction']) {
  const q = qualityHint(quality), [width, height] = sizes[q.resolution];
  return { width, height, fps: q.fps || 120, bitrate: Math.min(20_000_000, q.uploadMbps * 850_000), key: `${direction}:${width}:${height}:${q.fps}:${q.uploadMbps}` };
}
export function advertisedCodecs(direction: CodecReport['direction']): VideoCodec[] {
  try {
    const capabilities = direction === 'encode' ? globalThis.RTCRtpSender?.getCapabilities?.('video') : globalThis.RTCRtpReceiver?.getCapabilities?.('video');
    return [...new Set((capabilities?.codecs || []).map(c => CODECS.find(name => types[name].toLowerCase() === c.mimeType.toLowerCase())).filter((v): v is VideoCodec => !!v))];
  } catch { return []; }
}
export function cachedCodecReport(quality: Quality, direction: CodecReport['direction']): CodecReport | undefined {
  const item = cache.get(profile(quality, direction).key);
  return item && Date.now() - item.time < 300000 ? item.report : undefined;
}
export function probeCodecs(quality: Quality, direction: CodecReport['direction']): Promise<CodecReport> {
  const p = profile(quality, direction), old = cache.get(p.key);
  if (old && Date.now() - old.time < 300000) {
    if (old.report) return Promise.resolve(old.report);
    if (old.pending) return old.pending;
  }
  const entry: { time: number; report?: CodecReport; pending?: Promise<CodecReport> } = { time: Date.now() };
  const advertised = advertisedCodecs(direction);
  if (pendingProfiles >= 4) return Promise.resolve({ direction, codecs: advertised.map(codec => ({ codec, advertised: true })), width: p.width, height: p.height, fps: p.fps });
  pendingProfiles++;
  entry.pending = Promise.all(advertised.map(async codec => {
    const evidence: CodecEvidence = { codec, advertised: true };
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      if (typeof navigator === 'undefined' || !navigator.mediaCapabilities) return evidence;
      const query = direction === 'encode' ? navigator.mediaCapabilities.encodingInfo : navigator.mediaCapabilities.decodingInfo;
      if (typeof query !== 'function') return evidence;
      const configuration = { type: 'webrtc' as const, video: {
        contentType: types[codec], width: p.width, height: p.height, bitrate: p.bitrate, framerate: p.fps,
      } };
      const request: Promise<MediaCapabilitiesInfo> = direction === 'encode' ? navigator.mediaCapabilities.encodingInfo(configuration) : navigator.mediaCapabilities.decodingInfo(configuration);
      const result = await Promise.race([request, new Promise<undefined>(resolve => { timer = setTimeout(() => resolve(undefined), 800); })]);
      if (result) for (const key of ['supported', 'smooth', 'powerEfficient'] as const) if (typeof result[key] === 'boolean') evidence[key] = result[key];
    } catch { /* Missing WebRTC query support is unknown, never a global codec rejection. */ }
    finally { clearTimeout(timer); }
    return evidence;
  })).then(codecs => {
    const report: CodecReport = { direction, codecs, width: p.width, height: p.height, fps: p.fps };
    entry.report = report; return report;
  }).finally(() => { entry.pending = undefined; pendingProfiles--; });
  cache.set(p.key, entry);
  if (cache.size > 16) cache.delete(cache.keys().next().value!);
  return entry.pending;
}
export function codecOrder(mode: CodecMode, direction: CodecReport['direction'], report?: CodecReport): VideoCodec[] {
  const available = advertisedCodecs(direction);
  const known = available.length ? available : report?.codecs.filter(c => c.advertised).map(c => c.codec) || [];
  // Even older browsers without getCapabilities expose their true formats in
  // SDP. Compatibility only reorders those that actually exist there.
  if (mode === 'compatibility') return known.length ? CODECS.filter(c => known.includes(c)) : [...CODECS];
  if (!known.length) return [];
  if (mode !== 'auto') return known.includes(mode) ? [mode, ...known.filter(c => c !== mode)] : [];
  const score = (name: VideoCodec) => {
    const item = report?.codecs.find(c => c.codec === name);
    if (!item || item.supported === undefined) return 0;
    if (!item.supported || item.smooth === false) return -2;
    return item.powerEfficient === true && item.smooth === true ? 1 : item.powerEfficient === false ? -1 : 0;
  };
  const ranked = known.map((name, index) => ({ name, index, score: score(name) }));
  if (ranked.every(v => v.score === ranked[0].score)) return [];
  const best = Math.max(...ranked.map(v => v.score));
  // Only move positively supported candidates forward. Unknown/new codec
  // families and all fallback payloads otherwise keep the browser's order.
  return best > 0 ? ranked.filter(v => v.score === best).map(v => v.name) : [];
}

// PeerJS exposes SDP transformation after createOffer/createAnswer. Keep every
// original payload/profile, audio section and ICE attribute; only prefer order.
export function preferVideoCodecs(sdp: string, order: readonly VideoCodec[]): string {
  if (!order.length || sdp.length > 65536) return sdp;
  const separator = sdp.includes('\r\n') ? '\r\n' : '\n', lines = sdp.split(separator);
  for (let start = 0; start < lines.length; start++) {
    if (!lines[start].startsWith('m=video ')) continue;
    let end = start + 1; while (end < lines.length && !lines[end].startsWith('m=')) end++;
    const fields = lines[start].split(' '); if (fields.length < 4 || fields[1] === '0') continue;
    const names = new Map<string, string>(), apt = new Map<string, string>();
    for (const line of lines.slice(start + 1, end)) {
      const codec = /^a=rtpmap:(\d+) ([\w-]+)\//i.exec(line);
      if (codec) names.set(codec[1], codec[2].toLowerCase());
      const repair = /^a=fmtp:(\d+) .*\bapt=(\d+)(?:[;\s]|$)/i.exec(line);
      if (repair) apt.set(repair[1], repair[2]);
    }
    const payloads = fields.slice(3);
    const score = (payload: string) => {
      const name = names.get(apt.get(payload) || payload), index = order.findIndex(c => c === name);
      return index < 0 ? order.length : index;
    };
    if (!payloads.some(p => score(p) < order.length)) continue;
    const ranked = payloads.map((payload, index) => ({ payload, index, score: score(payload) })).sort((a, b) => a.score - b.score || a.index - b.index);
    lines[start] = [...fields.slice(0, 3), ...ranked.map(v => v.payload)].join(' ');
    start = end - 1;
  }
  return lines.join(separator);
}
export function codecTransform(quality: Quality, direction: CodecReport['direction']) {
  return (sdp: string) => preferVideoCodecs(sdp, codecOrder(codecMode(quality.codec), direction, cachedCodecReport(quality, direction)));
}
