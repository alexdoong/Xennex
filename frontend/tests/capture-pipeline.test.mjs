import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const directory = await mkdtemp(resolve('node_modules/.capture-pipeline-'));
const names = ['ImageDecoder', 'createImageBitmap', 'MediaStreamTrackGenerator', 'VideoFrame', 'MediaStream', 'document', 'Worker'];
const originals = Object.fromEntries(names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
let draws = 0, surfaces = 0, decodedClosed = 0, bitmapClosed = 0, rejectDrawing = false;
let workers = [], tracks = [], waitDecode;
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const frame = () => new ArrayBuffer(8);
try {
  for (const name of ['frameDecoder', 'captureVideoOutput', 'captureFrameWorkerOutput', 'captureFramePipeline']) {
    const source = (await readFile(`src/features/stream/${name}.ts`, 'utf8')).replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'");
    await writeFile(resolve(directory, `${name}.mjs`), ts.transpileModule(source, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
    }).outputText);
  }
  const { createCaptureFramePipeline } = await import(pathToFileURL(resolve(directory, 'captureFramePipeline.mjs')));
  const { CaptureOutputError } = await import(pathToFileURL(resolve(directory, 'captureVideoOutput.mjs')));
  class Track {
    stopped = false;
    constructor() { tracks.push(this); }
    stop() { this.stopped = true; }
    requestFrame() {}
  }
  globalThis.MediaStream = class {
    constructor(tracks) { this.tracks = tracks; }
    getTracks() { return this.tracks; }
    getVideoTracks() { return this.tracks; }
  };
  globalThis.ImageDecoder = class {
    async decode() {
      if (waitDecode) await waitDecode;
      let closed = false;
      return { image: { decoded: true, displayWidth: 80, displayHeight: 60,
        close() { assert.equal(closed, false, 'Every decoded frame has exactly one owner'); closed = true; decodedClosed++; } } };
    }
    close() {}
  };
  globalThis.createImageBitmap = async () => {
    let closed = false;
    return { width: 80, height: 60, close() { assert.equal(closed, false); closed = true; bitmapClosed++; } };
  };
  globalThis.document = { createElement() {
    surfaces++;
    return { getContext: () => ({ drawImage(image) {
      if (rejectDrawing && image.decoded) throw new TypeError('Fixture: VideoFrame drawing unsupported');
      draws++;
    } }), captureStream: () => new MediaStream([new Track()]) };
  } };
  globalThis.MediaStreamTrackGenerator = class extends Track {
    writable = new WritableStream();
  };
  const normal = createCaptureFramePipeline(30, 'motion');
  assert.throws(() => normal.stream, CaptureOutputError);
  const timing = await normal.write(frame());
  assert.equal(normal.path, 'canvas', 'Default remains compatible even when generator exists');
  assert.equal(normal.decoder, 'webcodecs');
  assert.equal(timing.communicationMs, 0); assert(timing.decodeMs >= 0 && timing.submitMs >= 0);
  const published = normal.stream;
  rejectDrawing = true;
  await normal.write(frame());
  assert.equal(normal.decoder, 'bitmap'); assert.equal(normal.stream, published);
  assert.equal(decodedClosed, 2); assert.equal(bitmapClosed, 1);
  normal.stop(); normal.stop();
  assert(published.getTracks().every(track => track.stopped));
  await assert.rejects(normal.write(frame()), { name: 'AbortError' });
  console.log('PASS: frame adapter retains published track through decoder fallback and owns every frame');

  rejectDrawing = false;
  let release;
  waitDecode = new Promise(resolve => { release = resolve; });
  const canceling = createCaptureFramePipeline(30, 'motion');
  const drawingBefore = draws;
  const pending = canceling.write(frame());
  canceling.stop(); release();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(draws, drawingBefore); assert.equal(decodedClosed, 3);
  waitDecode = undefined;
  console.log('PASS: stopping while decode is pending releases the late frame without drawing/publishing');

  globalThis.Worker = class {
    constructor() { workers.push(this); }
    postMessage(message, transfer) {
      if (message.type === 'configure') { queueMicrotask(() => this.onmessage?.({ data: { type: 'ready' } })); return; }
      if (message.type === 'stop') return;
      this.frame = structuredClone(message, { transfer });
    }
    reply(value) { this.onmessage?.({ data: value }); }
    terminate() { this.terminated = true; }
  };
  const surfacesBefore = surfaces;
  const worker = createCaptureFramePipeline(30, 'motion', 'worker');
  const nativeWorker = workers.at(-1);
  assert.throws(() => worker.stream, CaptureOutputError);
  const compressed = frame(), writing = worker.write(compressed);
  await tick(); assert.equal(compressed.byteLength, 0, 'Transferred buffer must not be reused by caller');
  await assert.rejects(worker.write(frame()), CaptureOutputError);
  nativeWorker.reply({ type: 'written', id: nativeWorker.frame.id, decodeMs: 1, submitMs: 1, decoder: 'bitmap' });
  await writing;
  assert.equal(worker.path, 'worker-generator'); assert.equal(worker.decoder, 'bitmap');
  assert.equal(surfaces, surfacesBefore, 'Worker mode must not allocate an unused canvas backend');
  const activeTrack = worker.stream.getVideoTracks()[0];
  const invalidReply = worker.write(frame()); await tick();
  nativeWorker.reply({ type: 'written', id: nativeWorker.frame.id, decodeMs: -1, submitMs: 1, decoder: 'bitmap' });
  await assert.rejects(invalidReply, CaptureOutputError);
  await assert.rejects(worker.write(frame()), CaptureOutputError);
  assert(activeTrack.stopped); worker.stop(); worker.stop();
  console.log('PASS: worker transfers ownership, bounds writes, rejects malformed timings and preserves failure classification');
} finally {
  for (const worker of workers) worker.terminate();
  for (const track of tracks) track.stop();
  for (const name of names) {
    if (originals[name]) Object.defineProperty(globalThis, name, originals[name]);
    else delete globalThis[name];
  }
  await rm(directory, { recursive: true, force: true });
}
