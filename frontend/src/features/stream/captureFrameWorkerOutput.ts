import { CaptureOutputError } from './captureVideoOutput';
import type { DecodePath } from './frameDecoder';

export type FrameWorkerRequest =
  | { type: 'configure'; writable: WritableStream<VideoFrame> }
  | { type: 'frame'; id: number; timestamp: number; data: ArrayBuffer }
  | { type: 'stop' };
export type FrameWorkerReply =
  | { type: 'ready' }
  | { type: 'written'; id: number; decodeMs: number; submitMs: number; decoder: DecodePath }
  | { type: 'failed' };
export interface WorkerFrameTiming { decodeMs: number; submitMs: number; decoder: DecodePath }

// Experimental native-JPEG consumer. Only compressed frames cross the UI thread;
// decoding and writing the transferred video stream happen in a dedicated worker.
export class CaptureFrameWorkerOutput {
  readonly stream: MediaStream;
  private track: MediaStreamTrack;
  private worker: Worker;
  private ready: Promise<void>;
  private resolveReady?: () => void;
  private rejectReady?: (error: Error) => void;
  private readyTimer?: ReturnType<typeof setTimeout>;
  private frameTimer?: ReturnType<typeof setTimeout>;
  private pending?: { id: number; resolve(value: WorkerFrameTiming): void; reject(error: Error): void };
  private sequence = 0;
  private timestamp = -1;
  private stopped = false;
  private failure?: CaptureOutputError;

  constructor(hint: string) {
    type Track = MediaStreamTrack & { writable: WritableStream<VideoFrame> };
    const Generator = (globalThis as typeof globalThis & { MediaStreamTrackGenerator?: new (options: { kind: 'video' }) => Track }).MediaStreamTrackGenerator;
    if (typeof Generator !== 'function' || typeof Worker !== 'function') throw new CaptureOutputError('Processamento de vídeo separado indisponível.');
    const track = new Generator({ kind: 'video' });
    this.track = track; this.stream = new MediaStream([track]);
    try {
      track.contentHint = hint;
      this.worker = new Worker(new URL('./captureFrameWorker.ts', import.meta.url), { type: 'module' });
      this.ready = new Promise((resolve, reject) => { this.resolveReady = resolve; this.rejectReady = reject; });
      void this.ready.catch(() => {});
      this.worker.onmessage = event => this.receive(event.data);
      this.worker.onerror = event => { event.preventDefault(); this.fail(); };
      this.worker.onmessageerror = () => this.fail();
      this.readyTimer = setTimeout(() => this.fail(), 3000);
      const message: FrameWorkerRequest = { type: 'configure', writable: track.writable };
      this.worker.postMessage(message, [track.writable]);
    } catch (error) { track.stop(); this.stop(); throw error; }
  }

  async write(data: ArrayBuffer): Promise<WorkerFrameTiming> {
    await this.ready;
    if (this.failure) throw this.failure;
    if (this.stopped) throw new DOMException('Captura cancelada', 'AbortError');
    if (this.pending || !data.byteLength || data.byteLength > 32 * 1024 * 1024) throw new CaptureOutputError('Quadro de vídeo fora dos limites.');
    this.timestamp = Math.max(this.timestamp + 1, Math.round(performance.now() * 1000));
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      this.pending = { id, resolve, reject };
      this.frameTimer = setTimeout(() => this.fail(), 4000);
      try {
        const message: FrameWorkerRequest = { type: 'frame', id, timestamp: this.timestamp, data };
        this.worker.postMessage(message, [data]);
      } catch { this.fail(); }
    });
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true; clearTimeout(this.readyTimer); clearTimeout(this.frameTimer); this.track?.stop();
    const canceled = new DOMException('Captura cancelada', 'AbortError');
    this.rejectReady?.(canceled); this.pending?.reject(canceled); this.pending = undefined;
    if (!this.worker) return;
    const worker = this.worker;
    worker.onmessage = worker.onerror = worker.onmessageerror = null;
    try { worker.postMessage({ type: 'stop' } satisfies FrameWorkerRequest); } catch { /* Worker already exited. */ }
    setTimeout(() => worker.terminate(), 200);
  }

  private receive(value: unknown) {
    if (this.stopped || this.failure || !value || typeof value !== 'object') return;
    const reply = value as Partial<FrameWorkerReply & WorkerFrameTiming> & { type?: string; id?: number };
    if (reply.type === 'ready') { clearTimeout(this.readyTimer); this.resolveReady?.(); return; }
    if (reply.type === 'failed') { this.fail(); return; }
    if (reply.type !== 'written' || !this.pending || reply.id !== this.pending.id) return;
    if (typeof reply.decodeMs !== 'number' || !Number.isFinite(reply.decodeMs) || reply.decodeMs < 0 || reply.decodeMs > 60000 ||
        typeof reply.submitMs !== 'number' || !Number.isFinite(reply.submitMs) || reply.submitMs < 0 || reply.submitMs > 60000 ||
        !['webcodecs', 'bitmap'].includes(String(reply.decoder))) { this.fail(); return; }
    const pending = this.pending; this.pending = undefined; clearTimeout(this.frameTimer);
    pending.resolve({ decodeMs: reply.decodeMs, submitMs: reply.submitMs, decoder: reply.decoder! });
  }
  private fail() {
    if (this.failure || this.stopped) return;
    this.failure = new CaptureOutputError('O processamento de vídeo separado foi interrompido. Reinicie esta transmissão.');
    clearTimeout(this.readyTimer); this.rejectReady?.(this.failure); this.pending?.reject(this.failure); this.pending = undefined;
    this.stop();
  }
}
