import type { DecodedCaptureFrame } from './frameDecoder';

type GeneratedTrack = MediaStreamTrack & { writable: WritableStream<VideoFrame> };
type GeneratorApi = typeof globalThis & {
  MediaStreamTrackGenerator?: new (options: { kind: 'video' }) => GeneratedTrack;
};
type CanvasTrack = MediaStreamTrack & { requestFrame?: () => void };
export type CaptureOutputPath = 'generator' | 'canvas';

export class CaptureOutputError extends Error {}

// A generated track accepts frames without waiting for a page paint. The optional
// Chromium API is detected, not assumed; canvas remains the compatibility path.
// LatestCaptureFrame serializes writes and retains only one pending JPEG upstream.
export class CaptureVideoOutput {
  private writer?: WritableStreamDefaultWriter<VideoFrame>;
  private track?: MediaStreamTrack;
  private media?: MediaStream;
  private canvas?: HTMLCanvasElement;
  private context?: CanvasRenderingContext2D;
  private stopped = false;
  private written = false;
  private busy = false;
  private timestamp = -1;
  readonly fps: number;
  private hint: string;
  path: CaptureOutputPath = 'canvas';

  constructor(fps: number, hint: string, mode: 'auto' | 'canvas' = 'auto') {
    this.fps = Math.max(1, Math.min(120, Number.isFinite(fps) ? fps : 30));
    this.hint = hint;
    const Generator = (globalThis as GeneratorApi).MediaStreamTrackGenerator;
    if (mode === 'canvas' || typeof Generator !== 'function' || typeof VideoFrame !== 'function') return;
    let generated: GeneratedTrack | undefined;
    try {
      generated = new Generator({ kind: 'video' });
      this.writer = generated.writable.getWriter();
      // Aborting/stopping deliberately rejects closed; never leak an unhandled rejection.
      void this.writer.closed.catch(() => {});
      generated.contentHint = hint;
      this.track = generated; this.media = new MediaStream([generated]); this.path = 'generator';
    } catch {
      generated?.stop(); this.discardWriter();
      this.track = this.media = undefined;
    }
  }

  get stream(): MediaStream {
    if (!this.written || !this.media || this.stopped) throw new CaptureOutputError('A saída de vídeo ainda não está pronta.');
    return this.media;
  }

  async write(frame: DecodedCaptureFrame): Promise<void> {
    this.check();
    if (this.busy) throw new CaptureOutputError('A saída de vídeo recebeu quadros simultâneos.');
    this.busy = true;
    try {
      if (this.writer) {
        try { await this.writeGenerated(frame); }
        catch (error) {
          this.check();
          // Before publication, a runtime/API failure can safely choose canvas.
          // Never replace an already published track silently.
          if (this.written) throw new CaptureOutputError('A saída de vídeo foi interrompida. Reinicie esta transmissão.', { cause: error });
          this.track?.stop(); this.discardWriter(); this.track = this.media = undefined;
          this.path = 'canvas';
          this.writeCanvas(frame);
        }
      } else this.writeCanvas(frame);
      this.check(); this.written = true;
    } finally { this.busy = false; }
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true; this.track?.stop(); this.discardWriter();
    // Release a potentially large backing surface without allocating a new one.
    if (this.canvas) { this.canvas.width = this.canvas.height = 0; }
    this.canvas = this.context = undefined; this.media = undefined;
  }

  private async writeGenerated(frame: DecodedCaptureFrame) {
    this.timestamp = Math.max(this.timestamp + 1, Math.round(performance.now() * 1000));
    const video = new VideoFrame(frame.source, { timestamp: this.timestamp });
    try { await this.writer!.write(video); }
    finally { video.close(); } // Also safe when the generator closed its owned frame.
  }

  private writeCanvas(frame: DecodedCaptureFrame) {
    this.canvas ??= document.createElement('canvas');
    this.context ??= this.canvas.getContext('2d', { alpha: false }) ?? undefined;
    if (!this.context) throw new CaptureOutputError('Não foi possível criar a superfície de vídeo.');
    if (this.canvas.width !== frame.width || this.canvas.height !== frame.height) {
      this.canvas.width = frame.width; this.canvas.height = frame.height;
    }
    this.context.drawImage(frame.source, 0, 0);
    if (!this.track) {
      let media = this.canvas.captureStream(0);
      let track = media.getVideoTracks()[0] as CanvasTrack;
      if (typeof track.requestFrame !== 'function') {
        media.getTracks().forEach(item => item.stop());
        media = this.canvas.captureStream(this.fps); track = media.getVideoTracks()[0];
      }
      try { track.contentHint = this.hint; }
      catch (error) { media.getTracks().forEach(item => item.stop()); throw error; }
      this.track = track; this.media = media;
    }
    (this.track as CanvasTrack).requestFrame?.();
  }

  private discardWriter() {
    const writer = this.writer; this.writer = undefined;
    if (writer) void writer.abort().catch(() => {}).finally(() => writer.releaseLock()).catch(() => {});
  }
  private check() { if (this.stopped) throw new DOMException('Captura cancelada', 'AbortError'); }
}
