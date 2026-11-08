import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const directory = await mkdtemp(resolve('node_modules/.capture-frames-'));
const originalCodec = globalThis.ImageDecoder, originalBitmap = globalThis.createImageBitmap;
try {
  for (const name of ['frameDecoder', 'latestFrame', 'streamStats']) {
    const source = await readFile(`src/features/stream/${name}.ts`, 'utf8');
    await writeFile(resolve(directory, name + '.mjs'), ts.transpileModule(source,
      { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  }
  const { CaptureFrameDecoder } = await import(pathToFileURL(resolve(directory, 'frameDecoder.mjs')));
  const { LatestCaptureFrame } = await import(pathToFileURL(resolve(directory, 'latestFrame.mjs')));
  const { sampleRtp } = await import(pathToFileURL(resolve(directory, 'streamStats.mjs')));
  const data = n => new Uint8Array([n]).buffer;
  const wait = () => new Promise(resolve => setTimeout(resolve, 0));
  let release, active = 0, maximum = 0, drops = 0;
  const seen = [];
  const queue = new LatestCaptureFrame(async bytes => {
    maximum = Math.max(maximum, ++active); seen.push(new Uint8Array(bytes)[0]);
    if (seen.length === 1) await new Promise(resolve => { release = resolve; });
    active--;
  }, () => drops++, error => { throw error; });
  const running = queue.push(data(1)); await wait(); queue.push(data(2)); queue.push(data(3)); release(); await running;
  assert.deepEqual(seen, [1, 3]); assert.equal(maximum, 1); assert.equal(drops, 1);
  await queue.push(data(4)); assert.deepEqual(seen, [1, 3, 4]);
  queue.stop(); await queue.push(data(5)); assert.deepEqual(seen, [1, 3, 4]);
  let errors = 0;
  const broken = new LatestCaptureFrame(() => { throw Error('Synthetic failure'); }, () => {}, () => errors++);
  await broken.push(data(1)); await broken.push(data(2)); assert.equal(errors, 2, 'Synchronous failure cannot wedge the sender');
  broken.stop();
  const stopped = [];
  const canceled = new LatestCaptureFrame(async bytes => { stopped.push(bytes.byteLength); await new Promise(resolve => { release = resolve; }); }, () => {}, () => {});
  const draining = canceled.push(data(1)); await wait(); canceled.push(data(2)); canceled.stop(); release(); await draining;
  assert.equal(stopped.length, 1, 'Cancellation discards pending JPEG');
  console.log('PASS: latest-frame queue serializes, replaces backlog, restarts after errors and discards pending work on stop');

  let frameCloses = 0, codecCloses = 0, bitmapCalls = 0;
  const bitmap = () => ({ width: 80, height: 60, close() { frameCloses++; } });
  const videoFrame = () => ({ displayWidth: 80, displayHeight: 60, close() { frameCloses++; } });
  globalThis.createImageBitmap = async () => { bitmapCalls++; return bitmap(); };
  globalThis.ImageDecoder = class {
    closed = false;
    async decode() { return { image: videoFrame() }; }
    close() { if (!this.closed) { this.closed = true; codecCloses++; } }
  };
  const codec = new CaptureFrameDecoder(); const frame = await codec.decode(data(1));
  assert.equal(codec.path, 'webcodecs'); assert.equal(frame.width, 80); assert.equal(codecCloses, 1); assert.equal(frameCloses, 0);
  frame.close(); assert.equal(frameCloses, 1); codec.stop();
  globalThis.ImageDecoder = class {
    async decode() { throw Error('Unsupported JPEG'); }
    close() { codecCloses++; }
  };
  const fallback = new CaptureFrameDecoder(); (await fallback.decode(data(1))).close();
  assert.equal(fallback.path, 'bitmap'); assert.equal(bitmapCalls, 1); fallback.stop();
  globalThis.ImageDecoder = undefined;
  const legacy = new CaptureFrameDecoder(); (await legacy.decode(data(1))).close(); assert.equal(legacy.path, 'bitmap'); legacy.stop();
  globalThis.ImageDecoder = class {
    async decode() { await new Promise(resolve => { release = resolve; }); return { image: videoFrame() }; }
    close() {}
  };
  const canceledCodec = new CaptureFrameDecoder(); const decoding = canceledCodec.decode(data(1));
  const before = frameCloses; canceledCodec.stop(); release(); await assert.rejects(decoding, { name: 'AbortError' });
  assert.equal(frameCloses, before + 1, 'Late decoded frame is closed without publication');
  assert.equal(bitmapCalls, 2, 'Cancellation must not start the compatibility decoder');
  console.log('PASS: WebCodecs owns/releases codecs and frames; unsupported API falls back; cancellation closes late frames');

  const first = sampleRtp({ timestamp: 1000, framesDecoded: 10, packetsReceived: 100, packetsLost: 0, totalDecodeTime: .01, jitterBufferDelay: .02, jitterBufferEmittedCount: 10, nackCount: 1 });
  const hiddenFirst = sampleRtp({ timestamp: 1000, framesReceived: 100, framesDecoded: 100 });
  const hiddenSecond = sampleRtp({ timestamp: 3000, framesReceived: 220, framesDecoded: 110 }, hiddenFirst.sample);
  assert.equal(hiddenSecond.reading.arrivalFps, 60); assert.equal(hiddenSecond.reading.fps, 5, 'Receiving and background decode rates must remain distinct');
  assert.equal(sampleRtp({ timestamp: 5000, framesReceived: 1 }, hiddenSecond.sample).reading.arrivalFps, undefined, 'Arrival counter reset is unknown, never a negative or frozen rate');
  assert.equal(sampleRtp({ timestamp: 30000, framesReceived: 400 }, hiddenSecond.sample).reading.arrivalFps, undefined, 'Suspended/stale samples do not invent an interval rate');
  const next = sampleRtp({ timestamp: 3000, framesDecoded: 130, packetsReceived: 200, packetsLost: 10, totalDecodeTime: .25, jitterBufferDelay: .26, jitterBufferEmittedCount: 130, nackCount: 4 }, first.sample);
  assert.equal(first.reading.health, undefined);
  assert(Math.abs(next.reading.health.decodeMs - 2) < 1e-6); assert(Math.abs(next.reading.health.jitterBufferMs - 2) < 1e-6);
  assert(Math.abs(next.reading.health.lossPercent - 100 / 11) < 1e-6); assert.equal(next.reading.health.nacks, 3);
  const reset = sampleRtp({ timestamp: 5000, framesDecoded: 1, totalDecodeTime: .001 }, next.sample);
  assert.equal(reset.reading.health.decodeMs, undefined); assert.equal(reset.reading.health.lossPercent, undefined);
  assert.equal(sampleRtp({ timestamp: 30000, framesDecoded: 140 }, next.sample).reading.health, undefined);
  console.log('PASS: RTP health measures interval averages/loss and keeps missing/reset/stale counters unknown');
} finally {
  globalThis.ImageDecoder = originalCodec; globalThis.createImageBitmap = originalBitmap;
  await rm(directory, { recursive: true, force: true });
}
