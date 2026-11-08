import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const directory = await mkdtemp(resolve('node_modules/.capture-output-'));
const names = ['MediaStreamTrackGenerator', 'VideoFrame', 'MediaStream', 'document'];
const original = Object.fromEntries(names.map(name => [name, globalThis[name]]));
const frame = { source: {}, width: 80, height: 60 };
let videos = [], tracks = [], failAt = 0, hold;
const tick = () => new Promise(done => setTimeout(done, 0));
try {
  const source = await readFile('src/features/stream/captureVideoOutput.ts', 'utf8');
  await writeFile(resolve(directory, 'output.mjs'), ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  const { CaptureVideoOutput, CaptureOutputError } = await import(pathToFileURL(resolve(directory, 'output.mjs')));
  globalThis.VideoFrame = class {
    constructor(source, options) { this.source = source; this.timestamp = options.timestamp; this.closed = false; videos.push(this); }
    close() { this.closed = true; }
  };
  globalThis.MediaStream = class {
    constructor(tracks) { this.tracks = tracks; }
    getTracks() { return this.tracks; }
    getVideoTracks() { return this.tracks; }
  };
  class Track {
    readyState = 'live';
    stop() { this.readyState = 'ended'; }
  }
  class Generator extends Track {
    writes = 0;
    constructor() {
      super(); tracks.push(this);
      this.writable = new WritableStream({ write: async video => {
        this.writes++;
        if (this.writes === failAt) throw new Error('Synthetic unsupported generator');
        if (hold) await hold;
        video.close();
      } });
    }
  }
  globalThis.MediaStreamTrackGenerator = Generator;
  const output = new CaptureVideoOutput(30, 'motion');
  assert.throws(() => output.stream, CaptureOutputError);
  await output.write(frame); await output.write(frame);
  assert.equal(output.path, 'generator'); assert.equal(tracks[0].contentHint, 'motion');
  assert.equal(output.stream.getVideoTracks()[0], tracks[0]);
  assert(videos.every(video => video.closed)); assert(videos[1].timestamp > videos[0].timestamp);
  output.stop(); output.stop(); assert.equal(tracks[0].readyState, 'ended');
  await assert.rejects(output.write(frame), { name: 'AbortError' });
  console.log('PASS: generated output owns/closes frames, uses monotonic timestamps and stops its exact track');

  let draws = 0, requests = 0;
  globalThis.document = { createElement: () => ({ getContext: () => ({ drawImage() { draws++; } }), captureStream() {
    const track = new Track(); track.requestFrame = () => requests++;
    return new MediaStream([track]);
  } }) };
  globalThis.MediaStreamTrackGenerator = undefined;
  const compatibility = new CaptureVideoOutput(30, 'detail');
  await compatibility.write(frame); assert.equal(compatibility.path, 'canvas');
  assert.equal(draws, 1); assert.equal(requests, 1); compatibility.stop();
  globalThis.MediaStreamTrackGenerator = Generator;
  failAt = 1;
  const unavailable = new CaptureVideoOutput(30, 'motion');
  const rejectedTrack = tracks.at(-1);
  await unavailable.write(frame);
  assert.equal(unavailable.path, 'canvas'); assert.equal(rejectedTrack.readyState, 'ended');
  assert.equal(unavailable.stream.getVideoTracks()[0].readyState, 'live'); unavailable.stop();
  console.log('PASS: absent/rejected generator falls back before publication, without leaking its rejected track');

  failAt = 2;
  const laterFailure = new CaptureVideoOutput(30, 'motion');
  await laterFailure.write(frame); const published = laterFailure.stream;
  await assert.rejects(laterFailure.write(frame), CaptureOutputError);
  assert.equal(laterFailure.path, 'generator'); assert.equal(laterFailure.stream, published, 'Published track is never swapped silently');
  laterFailure.stop();
  failAt = 0;
  let release; hold = new Promise(done => { release = done; });
  const pending = new CaptureVideoOutput(30, 'motion');
  const writing = pending.write(frame); await tick();
  await assert.rejects(pending.write(frame), CaptureOutputError);
  pending.stop(); release(); await assert.rejects(writing, { name: 'AbortError' }); await tick();
  assert(videos.every(video => video.closed)); assert(tracks.every(track => track.readyState === 'ended'));
  console.log('PASS: post-publication failure is explicit; cancellation/backpressure release pending frames without an unbounded queue');
} finally {
  for (const name of names) { if (original[name] === undefined) delete globalThis[name]; else globalThis[name] = original[name]; }
  await rm(directory, { recursive: true, force: true });
}
