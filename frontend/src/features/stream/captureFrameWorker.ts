import { CaptureFrameDecoder } from './frameDecoder';
import type { FrameWorkerRequest, FrameWorkerReply } from './captureFrameWorkerOutput';

// This module is executed only in a dedicated worker; no host objects or DOM.
const scope = globalThis as unknown as {
  onmessage: ((event: MessageEvent<FrameWorkerRequest>) => void) | null;
  postMessage(message: FrameWorkerReply): void;
};
const decoder = new CaptureFrameDecoder();
let writer: WritableStreamDefaultWriter<VideoFrame> | undefined;
let stopped = false, busy = false;
const stop = () => {
  stopped = true; decoder.stop();
  if (writer) void writer.abort().catch(() => {}).finally(() => writer?.releaseLock()).catch(() => {});
};
const failed = () => { if (!stopped) scope.postMessage({ type: 'failed' }); stop(); };
async function frame(message: Extract<FrameWorkerRequest, { type: 'frame' }>) {
  if (!writer || busy || !(message.data instanceof ArrayBuffer) || !message.data.byteLength || message.data.byteLength > 32 * 1024 * 1024 ||
      !Number.isSafeInteger(message.id) || message.id <= 0 || !Number.isSafeInteger(message.timestamp) || message.timestamp < 0) { failed(); return; }
  busy = true;
  try {
    const begin = performance.now(), image = await decoder.decode(message.data);
    let video: VideoFrame | undefined;
    const decoded = performance.now();
    try {
      if (stopped) return;
      video = new VideoFrame(image.source, { timestamp: message.timestamp });
      await writer.write(video);
      if (!stopped) scope.postMessage({ type: 'written', id: message.id, decodeMs: decoded - begin, submitMs: performance.now() - decoded, decoder: decoder.path });
    } finally { video?.close(); image.close(); }
  } catch { failed(); }
  finally { busy = false; }
}
scope.onmessage = ({ data }) => {
  if (stopped || !data || typeof data !== 'object') return;
  if (data.type === 'stop') { stop(); return; }
  if (data.type === 'configure') {
    if (writer || !(data.writable instanceof WritableStream) || typeof VideoFrame !== 'function') { failed(); return; }
    try { writer = data.writable.getWriter(); void writer.closed.catch(() => {}); scope.postMessage({ type: 'ready' }); }
    catch { failed(); }
    return;
  }
  if (data.type === 'frame') void frame(data);
};
