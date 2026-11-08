export interface DecodedCaptureFrame { source: CanvasImageSource; width: number; height: number; close(): void }
export type DecodePath = 'webcodecs' | 'bitmap';

// ImageDecoder avoids creating an intermediate ImageBitmap when VideoFrame drawing is supported.
// A new decoder owns each JPEG. Both its frame and codec are closed on every exit path.
export class CaptureFrameDecoder {
  private active?: ImageDecoder;
  private stopped = false;
  private codec: typeof ImageDecoder | undefined = typeof globalThis.ImageDecoder === 'function' ? globalThis.ImageDecoder : undefined;
  path: DecodePath = this.codec ? 'webcodecs' : 'bitmap';
  async decode(data: ArrayBuffer): Promise<DecodedCaptureFrame> {
    this.check();
    if (this.codec) {
      try {
        this.active = new this.codec({ data, type: 'image/jpeg', preferAnimation: false });
        const { image } = await this.active.decode({ frameIndex: 0 });
        if (this.stopped) { image.close(); this.check(); }
        return { source: image, width: image.displayWidth, height: image.displayHeight, close: () => image.close() };
      } catch (error) {
        if (this.stopped) throw error;
        this.codec = undefined; this.path = 'bitmap';
      } finally { this.active?.close(); this.active = undefined; }
    }
    const bitmap = await createImageBitmap(new Blob([data], { type: 'image/jpeg' }));
    if (this.stopped) { bitmap.close(); this.check(); }
    return { source: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close() };
  }
  // A browser can decode a VideoFrame yet reject drawing it: retry that JPEG via the compatibility path.
  useBitmap() { this.codec = undefined; this.path = 'bitmap'; }
  stop() { this.stopped = true; this.active?.close(); }
  private check() { if (this.stopped) throw new DOMException('Captura cancelada', 'AbortError'); }
}
