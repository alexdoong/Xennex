interface PendingFrame { data: ArrayBuffer; receivedAt: number }
// Exactly one active decode and one replaceable pending JPEG. Never build a latency backlog.
export class LatestCaptureFrame {
  private pending?: PendingFrame;
  private running?: Promise<void>;
  private stopped = false;
  private process: (data: ArrayBuffer, receivedAt: number) => Promise<void>;
  private dropped: () => void;
  private failed: (error: unknown) => void;
  constructor(process: (data: ArrayBuffer, receivedAt: number) => Promise<void>, dropped: () => void, failed: (error: unknown) => void) {
    this.process = process; this.dropped = dropped; this.failed = failed;
  }
  push(data: ArrayBuffer): Promise<void> {
    if (this.stopped) return Promise.resolve();
    if (!data.byteLength || data.byteLength > 32 * 1024 * 1024) { this.dropped(); return Promise.resolve(); }
    if (this.pending) this.dropped();
    this.pending = { data, receivedAt: performance.now() };
    this.running ??= Promise.resolve().then(() => this.drain());
    return this.running;
  }
  stop() { this.stopped = true; this.pending = undefined; }
  private async drain() {
    try {
      while (this.pending && !this.stopped) {
        const frame = this.pending; this.pending = undefined;
        try { await this.process(frame.data, frame.receivedAt); }
        catch (error) { if (!this.stopped) this.failed(error); }
      }
    } finally { this.running = undefined; }
  }
}
