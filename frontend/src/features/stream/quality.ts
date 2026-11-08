import type { CodecMode } from './streamCapabilities';
export const QUALITY_PRESETS = {
  '720p': { width: 1280, height: 720, label: '720p', bitrate: 4_000_000 },
  '1080p': { width: 1920, height: 1080, label: '1080p', bitrate: 8_000_000 },
  '1440p': { width: 2560, height: 1440, label: '1440p', bitrate: 12_000_000 },
  '2160p': { width: 3840, height: 2160, label: '2160p (4K)', bitrate: 20_000_000 },
  source: { width: 0, height: 0, label: 'Original', bitrate: 12_000_000 },
} as const;
export type Resolution = keyof typeof QUALITY_PRESETS;
export interface Quality { resolution: Resolution; fps: number; preference: 'motion' | 'detail'; uploadMbps: number; delivery?: 'preserve' | 'adaptive'; codec?: CodecMode }
export const DEFAULT_QUALITY: Quality = { resolution: '1080p', fps: 30, preference: 'motion', uploadMbps: 12, delivery: 'preserve' };
/** Zero means automatic, never a frozen zero-frame capture. */
export const requestedFps = (fps: number) => Number.isFinite(fps) ? Math.max(0, Math.min(120, Math.round(fps))) : 0;
export const captureFps = (fps: number) => requestedFps(fps) || 120;
export function fitWithin(width: number, height: number, maxWidth: number, maxHeight: number) {
  if (width <= 0 || height <= 0) return { width: 0, height: 0 };
  const scale = maxWidth > 0 && maxHeight > 0 ? Math.min(1, maxWidth / width, maxHeight / height) : 1;
  return { width: Math.max(2, Math.floor(width * scale / 2) * 2), height: Math.max(2, Math.floor(height * scale / 2) * 2) };
}
export function bitrateBudget(quality: Quality, viewers: number): number {
  const ceiling = Math.max(1, Math.min(1000, Number.isFinite(quality.uploadMbps) ? quality.uploadMbps : 12)) * 1_000_000 * 0.85 / Math.max(1, viewers);
  return Math.max(1_000, Math.min(QUALITY_PRESETS[quality.resolution].bitrate * captureFps(quality.fps) / 30, ceiling));
}
const tuning = new WeakMap<RTCPeerConnection, Promise<void>>();
const warnings = new WeakMap<RTCPeerConnection, string>();
export const qualityWarning = (connection: RTCPeerConnection) => warnings.get(connection) || '';
export function tuneConnection(connection: RTCPeerConnection, quality: Quality, viewers: number): Promise<void> {
  const next = (tuning.get(connection) || Promise.resolve()).catch(() => {}).then(() => applyQuality(connection, quality, viewers));
  tuning.set(connection, next);
  return next;
}
async function applyQuality(connection: RTCPeerConnection, quality: Quality, viewers: number) {
  for (const sender of connection.getSenders()) {
    if (sender.track?.kind !== 'video') continue;
    sender.track.contentHint = quality.preference;
    const params = sender.getParameters();
    // Encodings cannot be added after negotiation; retry when connected instead.
    if (!params.encodings?.length) continue;
    for (const encoding of params.encodings) {
      encoding.maxBitrate = bitrateBudget(quality, viewers);
      encoding.maxFramerate = captureFps(quality.fps);
      encoding.scaleResolutionDownBy = 1;
    }
    params.degradationPreference = quality.delivery !== 'adaptive' || quality.preference === 'detail' ? 'maintain-resolution' : 'balanced';
    try { await sender.setParameters(params); warnings.delete(connection); }
    catch (error) { warnings.set(connection, 'O navegador não aplicou os parâmetros de qualidade solicitados.'); console.warn('[Stream] Ajuste de qualidade não aplicado:', error); }
  }
}
