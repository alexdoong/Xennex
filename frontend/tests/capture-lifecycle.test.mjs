import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const directory = await mkdtemp(resolve('node_modules/.capture-lifecycle-'));
const captures = [];
try {
  for (const name of ['quality', 'iceConfig', 'captureSocket', 'captureStartup', 'captureMetrics', 'frameDecoder', 'latestFrame', 'captureVideoOutput', 'captureFrameWorkerOutput', 'captureFramePipeline', 'browserCaptureSupport', 'capture']) {
    const source = (await readFile(`src/features/stream/${name}.ts`, 'utf8')).replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'");
    await writeFile(resolve(directory, `${name}.mjs`), ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  }
  const { captureAwait, waitCaptureState } = await import(pathToFileURL(resolve(directory, 'captureStartup.mjs')));
  const { startCapture } = await import(pathToFileURL(resolve(directory, 'capture.mjs')));
  const { parseCaptureMetrics, CaptureFrameTimings } = await import(pathToFileURL(resolve(directory, 'captureMetrics.mjs')));
  const metrics = { type: 'capture-metrics', version: 1, sourceWidth: 3840, sourceHeight: 2160, outputWidth: 1920, outputHeight: 1080,
    scalePath: 'gpu', mappedBytes: 8294400, sourceBytes: 33177600, samples: 121, windowMs: 2000, processedFps: 60,
    mapMs: 1, beforeJpegMs: 2, jpegMs: 3, totalMs: 5, p95Ms: 8 };
  assert.equal(parseCaptureMetrics(JSON.stringify(metrics)).mappedBytes, 8294400);
  for (const invalid of [{ ...metrics, version: 2 }, { ...metrics, mappedBytes: -1 }, { ...metrics, samples: 999 },
    { ...metrics, scalePath: '<script>' }, { ...metrics, outputWidth: 0 }, { ...metrics, totalMs: '5' }])
    assert.equal(parseCaptureMetrics(JSON.stringify(invalid)), undefined);
  assert.equal(parseCaptureMetrics('x'.repeat(4097)), undefined);
  const timings = new CaptureFrameTimings();
  for (let i = 0; i < 300; i++) timings.add(2, 4);
  assert.deepEqual(timings.take(), { decodeMs: 2, drawMs: 4, decodeP95Ms: 2, queueMs: 0, ageP95Ms: 6, receivedFrames: 0, replacedFrames: 0 }); assert.deepEqual(timings.take(), {});
  timings.add(2, 3);
  const submission = timings.take('generator');
  assert.equal(submission.submitMs, 3); assert.equal(submission.drawMs, undefined, 'Generator submission is not a canvas paint');
  console.log('PASS: bounded native pipeline telemetry rejects malformed fields and separates canvas timing');
  const { DEFAULT_QUALITY, tuneConnection, qualityWarning } = await import(pathToFileURL(resolve(directory, 'quality.mjs')));
  let rejectQuality = true;
  const connection = { getSenders: () => [{ track: { kind: 'video' }, getParameters: () => ({ encodings: [{}] }),
    async setParameters() { if (rejectQuality) throw new Error('Synthetic unsupported encoder'); } }] };
  await tuneConnection(connection, DEFAULT_QUALITY, 1); assert.match(qualityWarning(connection), /não aplicou/);
  rejectQuality = false;
  await tuneConnection(connection, DEFAULT_QUALITY, 1); assert.equal(qualityWarning(connection), '');
  console.log('PASS: rejected quality settings remain visible and clear after a successful retry');
  const { parseIceConfig } = await import(pathToFileURL(resolve(directory, 'iceConfig.mjs')));
  assert.equal(parseIceConfig('[{"urls":[12,"turn:server"]}]').hasTurn, false);
  assert.equal(parseIceConfig('broken turn:server').hasTurn, false);
  assert.equal(parseIceConfig('[{"urls":"https://example.test"}]').invalid, true);
  assert.equal(parseIceConfig('[{"urls":"turns:example.test:5349?transport=tcp","username":"fixture","credential":"fixture"}]').hasTurn, true);
  console.log('PASS: TURN is advertised only for validated ICE configuration');
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let released = 0;
  await assert.rejects(captureAwait(pending, new AbortController().signal, 15, 'timeout', () => { released++; }), /timeout/);
  release({}); await delay(5); assert.equal(released, 1);
  await assert.rejects(waitCaptureState(async () => JSON.stringify({ phase: 'active', video: 'starting', audio: 'idle' }),
    'video', 'ready', new AbortController().signal, 20), /não respondeu/);
  console.log('PASS: startup deadlines and late acquisitions release resources');

  let choose;
  const permission = new Promise(resolve => { choose = resolve; });
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getDisplayMedia: () => permission } } });
  globalThis.window = {};
  const cancellation = new AbortController();
  const selecting = startCapture({ source: 'browser', audio: 'none', quality: DEFAULT_QUALITY }, cancellation.signal, () => {});
  cancellation.abort();
  await assert.rejects(selecting, { name: 'AbortError' });
  let lateStops = 0;
  choose({ getTracks: () => [{ stop() { lateStops++; } }] }); await delay(5);
  assert.equal(lateStops, 1);
  console.log('PASS: cancel during browser picker settles immediately and stops late media');

  for (const requested of [60, 0]) {
    let configured = false, appliedConstraints;
    const track = { kind: 'video', readyState: 'live', addEventListener() {}, stop() { this.readyState = 'ended'; },
      getSettings: () => configured ? { width: 1280, height: 720, frameRate: 24 } : { width: 1920, height: 1080, frameRate: 60 },
      async applyConstraints(value) { appliedConstraints = value; configured = true; } };
    const media = { getTracks: () => [track], getVideoTracks: () => [track], getAudioTracks: () => [] };
    navigator.mediaDevices.getDisplayMedia = async () => media;
    const capture = await startCapture({ source: 'browser', audio: 'none', quality: { ...DEFAULT_QUALITY, fps: requested } }, new AbortController().signal, () => {});
    assert.match(capture.warning, /1280 × 720/);
    if (requested) {
      assert.match(capture.warning, /24 FPS.*60 FPS/);
      assert.equal(appliedConstraints.frameRate.max, requested);
    } else assert.equal('frameRate' in appliedConstraints, false, 'Automatic mode must not force 120 FPS after selection');
    await capture.stop(); assert.equal(track.readyState, 'ended');
  }
  console.log('PASS: silently reduced capture format is reported; automatic FPS does not force a capture rate');

  const fixture = async (manual = true, hybrid = false, desktop = false, rejectVideoFrame = false, game = false) => {
    const makeTrack = kind => ({ kind, readyState: 'live', stop() { this.readyState = 'ended'; }, addEventListener() {} });
    const video = makeTrack('video'), audio = makeTrack('audio'); const tracks = [video];
    let requestedFrames = 0;
    if (manual) video.requestFrame = () => { requestedFrames++; };
    const canvasRates = [];
    const stream = { getTracks: () => tracks, getVideoTracks: () => [video], getAudioTracks: () => tracks.filter(t => t.kind === 'audio'), addTrack: t => tracks.push(t) };
    let owned = false, state = 'ready', ended = 0, stoppedAudio = 0, nativeVideoStarts = 0, browserVideoStarts = 0, browserOptions;
    const warnings = [], phases = [], sockets = [];
    const desktopCalls = [];
    const gameCalls = [], audioCalls = [];
    video.getSettings = () => ({ width: 800, height: 600, frameRate: 30 }); video.applyConstraints = async () => {};
    navigator.mediaDevices.getDisplayMedia = async options => { browserOptions = options; return stream; };
    globalThis.window = { chrome: { webview: { postMessage() {}, hostObjects: { api: {
      GetCaptureToken: async () => 'a'.repeat(64), TryBeginCapture: async () => { owned = true; return true; },
      BeginNativeCapture: async () => { nativeVideoStarts++; return true; }, BeginCaptureAudio: async (...args) => { audioCalls.push(args); return true; },
      BeginGameCapture: async (...args) => { gameCalls.push(args); return true; },
      BeginBrowserCapture: async () => { browserVideoStarts++; return true; },
      BeginDesktopCapture: async (...args) => { desktopCalls.push(args); return true; },
      GetCaptureState: async () => JSON.stringify({ phase: owned ? 'active' : 'idle', video: 'ready', audio: state }),
      GetProcessAudioFormat: async () => JSON.stringify({ sampleRate: 48000, channels: 2 }),
      StopCaptureAudio: async () => { stoppedAudio++; }, EndCapture: async () => { owned = false; },
    } } } } };
    globalThis.document = { createElement: () => ({ getContext: () => ({ drawImage(image) { if (rejectVideoFrame && image.syntheticVideoFrame) throw new Error('Unsupported VideoFrame canvas'); } }), captureStream(rate) {
      canvasRates.push(rate);
      return !manual && rate === 0 ? { getVideoTracks: () => [makeTrack('video')], getTracks: () => [] } : stream;
    } }) };
    globalThis.createImageBitmap = async () => ({ width: 800, height: 600, close() {} });
    globalThis.AudioContext = class {
      currentTime = 0; state = 'running'; async resume() {} async close() { this.state = 'closed'; }
      createMediaStreamDestination() { return { stream: { getAudioTracks: () => [audio] } }; }
    };
    globalThis.WebSocket = class {
      constructor(url) {
        this.url = url; sockets.push(this);
        setTimeout(() => { this.onopen?.(); if (url.includes('videostream')) setTimeout(() => this.onmessage?.({ data: new ArrayBuffer(4) }), 5); }, 1);
      }
      close() { this.onclose?.(); }
    };
    const capture = await startCapture({ source: game ? 'game' : hybrid ? 'browser' : desktop ? 'monitor' : 'window', monitorBackend: 'dxgi', monitorId: 'chosen-display', process: { Hwnd: 111, Pid: 11 }, audioProcess: { Pid: 22 }, audio: hybrid || game ? 'process' : 'system', quality: DEFAULT_QUALITY },
      new AbortController().signal, () => { ended++; }, { onWarning: message => warnings.push(message), onProgress: phase => phases.push(phase) });
    captures.push(capture);
    return { capture, video, audio, warnings, phases, canvasRates, browserOptions, nativeVideoStarts, browserVideoStarts, desktopCalls, gameCalls, audioCalls, get requestedFrames() { return requestedFrames; },
      status: value => sockets.find(s => s.url.includes('videostream')).onmessage({ data: JSON.stringify(value) }),
      frame: () => sockets.find(s => s.url.includes('videostream')).onmessage({ data: new ArrayBuffer(4) }), socket: sockets.find(s => s.url.includes('audiostream')),
      failWorker() { state = 'error'; }, get ended() { return ended; }, get stoppedAudio() { return stoppedAudio; } };
  };
  const dropped = await fixture();
  assert.equal(dropped.desktopCalls.length, 0, 'Window capture cannot silently become desktop capture');
  assert.deepEqual(dropped.canvasRates, [0]); assert.equal(dropped.requestedFrames, 1, 'First decoded frame explicitly captured');
  await dropped.status(metrics);
  assert.equal(dropped.capture.pipeline.worker.scalePath, 'gpu', 'WGC receives telemetry without requiring DXGI status handling');
  await dropped.status({ ...metrics, outputWidth: -1 });
  assert.equal(dropped.capture.pipeline.worker.outputWidth, 1920, 'Malformed telemetry does not replace the last valid measurement');
  await dropped.frame(); assert.equal(dropped.requestedFrames, 2, 'Each new decoded frame explicitly captured');
  assert.deepEqual(dropped.phases, ['video', 'frame', 'audio']);
  dropped.socket.close(); await delay(5);
  assert.equal(dropped.audio.readyState, 'ended'); assert.equal(dropped.video.readyState, 'live');
  assert.equal(dropped.ended, 0); assert.equal(dropped.stoppedAudio, 1); assert.match(dropped.capture.warning, /interrompido/);
  assert.equal(dropped.warnings.length, 1);
  await dropped.capture.stop();
  console.log('PASS: disconnected audio is stopped and reported while video continues');
  const worker = await fixture();
  await delay(1100); assert.equal(worker.warnings.length, 0, 'Silence is not a worker failure');
  worker.failWorker(); await delay(1100);
  assert.equal(worker.warnings.length, 1); assert.equal(worker.audio.readyState, 'ended');
  await worker.capture.stop(); await delay(1100); assert.equal(worker.warnings.length, 1);
  console.log('PASS: worker failure is reported, legitimate silence and explicit stop produce no false warnings');
  const fallback = await fixture(false);
  assert.deepEqual(fallback.canvasRates, [0, 30], 'Unsupported manual capture falls back to requested automatic FPS');
  assert.equal(fallback.video.readyState, 'live'); await fallback.capture.stop();
  console.log('PASS: manual canvas capture requests each decoded frame and preserves an automatic fallback');
  const savedDecoder = globalThis.ImageDecoder;
  globalThis.ImageDecoder = class {
    async decode() { return { image: { syntheticVideoFrame: true, displayWidth: 800, displayHeight: 600, close() {} } }; }
    close() {}
  };
  const incompatible = await fixture(true, false, false, true);
  await incompatible.status(metrics);
  assert.equal(incompatible.capture.pipeline.decoder, 'bitmap'); assert.equal(incompatible.video.readyState, 'live');
  assert.equal(incompatible.requestedFrames, 1, 'Rejected VideoFrame drawing retries the same JPEG without losing startup');
  await incompatible.capture.stop(); globalThis.ImageDecoder = savedDecoder;
  console.log('PASS: unsupported VideoFrame canvas transparently falls back to ImageBitmap before publishing');
  const hybrid = await fixture(true, true);
  assert.deepEqual(hybrid.phases, ['selecting', 'video', 'audio']);
  assert.equal(hybrid.capture.nativeSession, true); assert.equal(hybrid.browserOptions.audio, false, 'No duplicate browser/system audio');
  assert.equal(hybrid.nativeVideoStarts, 0); assert.equal(hybrid.browserVideoStarts, 1);
  assert.deepEqual(hybrid.canvasRates, [], 'Browser video never passes through the native JPEG canvas');
  assert.equal(hybrid.capture.stream.getAudioTracks().length, 1);
  hybrid.socket.close(); await delay(5);
  assert.equal(hybrid.video.readyState, 'live'); assert.equal(hybrid.audio.readyState, 'ended');
  await hybrid.capture.stop(); assert.equal(hybrid.video.readyState, 'ended');
  console.log('PASS: hybrid capture keeps browser video, attaches only process audio and isolates audio failure');
  const desktop = await fixture(true, false, true);
  await assert.rejects(startCapture({ source: 'monitor', monitorBackend: 'dxgi', audio: 'none', quality: DEFAULT_QUALITY }, new AbortController().signal, () => {}), /Escolha o monitor/);
  assert.equal(desktop.nativeVideoStarts, 0, 'Explicit DXGI does not call WGC');
  assert.equal(desktop.desktopCalls.length, 1);
  assert.deepEqual(desktop.desktopCalls[0].slice(1), ['chosen-display', 30, '1080p']);
  await desktop.status({ type: 'capture-status', phase: 'recovering', message: 'untrusted text' });
  assert.match(desktop.capture.warning, /Recuperando/); assert(!desktop.capture.warning.includes('untrusted'));
  const beforeRepeated = desktop.warnings.length;
  await desktop.status({ type: 'capture-status', phase: 'recovering' });
  assert.equal(desktop.warnings.length, beforeRepeated);
  await desktop.status({ type: 'capture-status', phase: 'ready' }); assert.equal(desktop.capture.warning, '');
  await desktop.status({ type: 'capture-status', phase: 'unstable', message: 'untrusted text' });
  assert.match(desktop.capture.warning, /sem bordas/); assert(!desktop.capture.warning.includes('untrusted'));
  await desktop.status({ type: 'capture-status', phase: 'ready' }); assert.equal(desktop.capture.warning, '');
  desktop.socket.close(); await delay(5); assert.match(desktop.capture.warning, /áudio foi interrompido/);
  await desktop.status({ type: 'capture-status', phase: 'recovering' });
  await desktop.status({ type: 'capture-status', phase: 'ready' });
  assert.match(desktop.capture.warning, /áudio foi interrompido/, 'Recovery must preserve independent audio warnings');
  assert.equal(desktop.video.readyState, 'live'); await desktop.capture.stop();
  console.log('PASS: DXGI pins explicit monitor, handles recovery status and preserves independent audio warnings; window capture never escalates');
  const game = await fixture(true, false, false, false, true);
  assert.equal(game.nativeVideoStarts, 0); assert.equal(game.desktopCalls.length, 0);
  assert.deepEqual(game.gameCalls[0].slice(1), [111, 11, 30, '1080p']);
  assert.equal(game.audioCalls[0][1], 22, 'Game video keeps independent audio-process selection');
  assert.equal(game.video.readyState, 'live'); await game.capture.stop(); assert.equal(game.video.readyState, 'ended');
  await assert.rejects(startCapture({ source: 'game', audio: 'none', quality: DEFAULT_QUALITY }, new AbortController().signal, () => {}), /Selecione uma janela/);
  console.log('PASS: game hook is explicit, preserves selected HWND/PID/quality and independent audio, without window/monitor fallback');
} finally {
  await Promise.all(captures.map(capture => capture.stop()));
  await rm(directory, { recursive: true, force: true });
}
