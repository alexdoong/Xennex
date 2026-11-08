import { CaptureFrameDecoder, type DecodePath, type DecodedCaptureFrame } from './frameDecoder';
import { CaptureVideoOutput, CaptureOutputError } from './captureVideoOutput';
import { CaptureFrameWorkerOutput } from './captureFrameWorkerOutput';

// Internal selection only. Experimental outputs are not product capability claims.
export type CaptureFrameMode = 'canvas' | 'auto' | 'worker';
export type CaptureFramePath = 'canvas' | 'generator' | 'worker-generator';
export interface FrameProcessingTiming { decodeMs: number; submitMs: number; communicationMs: number }
export interface CaptureFramePipeline {
  readonly stream: MediaStream;
  readonly path: CaptureFramePath;
  readonly decoder: DecodePath | undefined;
  // Serial caller (LatestCaptureFrame). Takes ownership of data; worker may detach it.
  write(data: ArrayBuffer): Promise<FrameProcessingTiming>;
  stop(): void;
}

// Decode/draw compatibility belongs to this adapter, not the session coordinator.
class MainThreadFramePipeline implements CaptureFramePipeline {
  private readonly frameDecoder = new CaptureFrameDecoder();
  private readonly output: CaptureVideoOutput;
  private stopped = false;

  constructor(fps: number, hint: string, mode: 'canvas' | 'auto') {
    this.output = new CaptureVideoOutput(fps, hint, mode);
  }
  get stream() { return this.output.stream; }
  get path() { return this.output.path; }
  get decoder() { return this.frameDecoder.path; }

  async write(data: ArrayBuffer): Promise<FrameProcessingTiming> {
    this.check();
    const begin = performance.now();
    let frame: DecodedCaptureFrame | undefined = await this.frameDecoder.decode(data);
    let decoded = performance.now();
    try {
      this.check();
      try { await this.output.write(frame); }
      catch (error) {
        this.check();
        if (this.decoder !== 'webcodecs' || this.path !== 'canvas' || error instanceof CaptureOutputError) throw error;
        const previous = frame;
        frame = undefined;
        previous.close();
        this.frameDecoder.useBitmap();
        frame = await this.frameDecoder.decode(data);
        decoded = performance.now();
        this.check();
        await this.output.write(frame);
      }
      this.check();
      return { decodeMs: decoded - begin, submitMs: performance.now() - decoded, communicationMs: 0 };
    } finally { frame?.close(); }
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.frameDecoder.stop();
    this.output.stop();
  }
  private check() { if (this.stopped) throw new DOMException('Captura cancelada', 'AbortError'); }
}

class WorkerFramePipeline implements CaptureFramePipeline {
  private readonly output: CaptureFrameWorkerOutput;
  private written = false;
  private stopped = false;
  readonly path = 'worker-generator';
  decoder: DecodePath | undefined;

  constructor(hint: string) { this.output = new CaptureFrameWorkerOutput(hint); }
  get stream() {
    if (!this.written || this.stopped) throw new CaptureOutputError('A saída de vídeo ainda não está pronta.');
    return this.output.stream;
  }
  async write(data: ArrayBuffer): Promise<FrameProcessingTiming> {
    const begin = performance.now();
    const measured = await this.output.write(data);
    if (this.stopped) throw new DOMException('Captura cancelada', 'AbortError');
    this.decoder = measured.decoder;
    this.written = true;
    return { ...measured, communicationMs: Math.max(0, performance.now() - begin - measured.decodeMs - measured.submitMs) };
  }
  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.output.stop();
  }
}

export function createCaptureFramePipeline(fps: number, hint: string, mode: CaptureFrameMode = 'canvas'): CaptureFramePipeline {
  // Instantiate exactly one backend. No idle canvas/decoder alongside the worker.
  return mode === 'worker' ? new WorkerFramePipeline(hint) : new MainThreadFramePipeline(fps, hint, mode);
}
