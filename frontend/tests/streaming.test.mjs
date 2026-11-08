import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
import { mock } from 'node:test';

const directory = await mkdtemp(resolve('node_modules/.xennex-stream-tests-'));
const clients = [];
const wait = () => new Promise(resolve => setTimeout(resolve, 15));
try {
  for (const name of ['workspaceProtocol', 'RoomWorkspaceState', 'RoomWorkspaceClient', 'protocol', 'quality', 'streamCapabilities', 'streamStats', 'iceConfig', 'turnFallback', 'entryDiagnostics', 'sessionBenchmark', 'connectionDiagnostics', 'captureSocket', 'captureStartup', 'captureMetrics', 'frameDecoder', 'latestFrame', 'captureVideoOutput', 'captureFrameWorkerOutput', 'captureFramePipeline', 'browserCaptureSupport', 'capture', 'stageLayout', 'stagePreferences', 'RoomCoordinator', 'RoomClient']) {
    let source = await readFile(`src/features/stream/${name}.ts`, 'utf8');
    if (name === 'RoomClient') source = source.replace(/import .*? from 'peerjs';/, 'const Peer = class {};').replace("import { HAS_TURN, peerOptions } from './peerConfig';", 'const HAS_TURN = false; const peerOptions = () => ({});');
    source = source.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'");
    await writeFile(resolve(directory, `${name}.mjs`), ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  }
  const protocol = await import(pathToFileURL(resolve(directory, 'protocol.mjs')));
  const quality = await import(pathToFileURL(resolve(directory, 'quality.mjs')));
  const { RoomClient } = await import(pathToFileURL(resolve(directory, 'RoomClient.mjs')));
  const { RoomCoordinator } = await import(pathToFileURL(resolve(directory, 'RoomCoordinator.mjs')));
  const { EntryDiagnostics, entryReport } = await import(pathToFileURL(resolve(directory, 'entryDiagnostics.mjs')));
  let entryClock = 0;
  const entryProbe = new EntryDiagnostics(() => entryClock);
  entryClock = 100; entryProbe.stage('coordinator'); entryProbe.negotiate();
  entryProbe.observe({ ice: 'failed', connection: 'failed', gathering: 'complete', host: 4, public: 1, relay: 0, errorCode: 701 });
  entryProbe.observe({ ice: 'SECRET_IP_SDP', errorCode: 701, relay: -9 });
  entryClock = 2200; entryProbe.finish('transport');
  const entryValue = entryProbe.snapshot();
  assert.equal(entryValue.ice, 'failed'); assert.equal(entryValue.elapsedMs, 2200);
  assert.deepEqual(entryValue.errors, [701]); assert.equal(entryValue.candidates.relay, 0);
  entryProbe.stage('ready'); assert.equal(entryProbe.snapshot().stage, 'transport', 'Late events cannot turn failure into success');
  const safeReport = entryReport(entryValue, 'error', false);
  assert(!safeReport.includes('SECRET')); assert(safeReport.includes('causa ainda não foi confirmada'));
  entryValue.timeline.length = 0; assert(entryProbe.snapshot().timeline.length > 0, 'Snapshots cannot mutate diagnostic history');
  const many = new EntryDiagnostics(() => entryClock);
  for (let i = 0; i < 60; i++) { many.negotiate(); many.stage('confirmation'); many.observe({ errorCode: i }); }
  assert(many.snapshot().timeline.length <= 16); assert(many.snapshot().errors.length <= 8);
  many.finish(); assert.equal(many.snapshot().result, 'connected');
  console.log('PASS: bounded entry stages, privacy-safe reports, failure classification and immutable snapshots');
  class EntryPeer extends EventEmitter {
    destroyed = false; disconnected = false; options = {}; channel;
    connect() { return this.channel; }
    destroy() { this.destroyed = true; }
  }
  for (const expected of ['signaling', 'transport', 'confirmation']) {
    const peer = new EntryPeer();
    peer.channel = Object.assign(new EventEmitter(), { open: false, send() {}, close() {} });
    const client = new RoomClient(() => peer);
    mock.timers.enable({ apis: ['Date'] });
    try {
      client.start('XNX-PRIVATE-ROOM', 'PRIVATE NAME', false);
      if (expected !== 'signaling') peer.emit('open', 'PRIVATE_PEER_ID');
      if (expected === 'confirmation') { peer.channel.open = true; peer.channel.emit('open'); }
      mock.timers.tick(61000); client.tick();
      assert.equal(client.getSnapshot().entry.failure, expected);
      const report = entryReport(client.getSnapshot().entry, client.getSnapshot().phase, false);
      assert(!/PRIVATE|XNX-PRIVATE/.test(report));
      client.leave(); assert.equal(client.getSnapshot().entry, null);
    } finally { client.leave(); mock.timers.reset(); }
  }
  console.log('PASS: signaling, ICE/channel and admission timeouts classified separately; reports survive failure and clear on leave');
  const synchronousFailure = new RoomClient(() => { throw new Error('PRIVATE ERROR'); });
  synchronousFailure.start('XNX-SYNC-FAIL', 'Private', false);
  assert.equal(synchronousFailure.getSnapshot().phase, 'error', 'Synchronous Peer construction failure cannot leave a permanently busy lobby');
  assert.equal(synchronousFailure.getSnapshot().entry.failure, 'signaling'); synchronousFailure.leave();
  for (const expected of ['coordinator', 'transport']) {
    const peer = new EntryPeer(); peer.connect = () => { throw new Error('PRIVATE CONNECT ERROR'); };
    const client = new RoomClient(id => { if (id) throw new Error('PRIVATE REGISTRATION ERROR'); return peer; });
    mock.timers.enable({ apis: ['Date'] });
    try {
      client.start('XNX-SYNC-BOUNDED', 'Private', expected === 'coordinator');
      peer.emit('open', 'private-self-id');
      assert.equal(client.getSnapshot().phase, 'connecting');
      mock.timers.tick(61000); client.tick();
      assert.equal(client.getSnapshot().entry.failure, expected);
    } finally { client.leave(); mock.timers.reset(); }
  }
  console.log('PASS: synchronous peer, coordinator and channel failures are bounded and leave no permanently loading lobby');
  class Handshake extends EventEmitter {
    peer = 'pending'; open = false; closed = false; sent = [];
    send(message) { this.sent.push(message); }
    close() { if (this.closed) return; this.closed = true; this.open = false; this.emit('close'); }
  }
  mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  try {
    const hub = new RoomCoordinator('pending', []), pending = new Handshake();
    hub.accept(pending); mock.timers.tick(12000);
    assert(!pending.closed, 'Inbound offer must survive more than 10 seconds before DataChannel opens');
    pending.open = true; pending.emit('open'); mock.timers.tick(9000);
    assert(!pending.closed, 'Join budget starts after channel opens');
    pending.emit('data', { type: 'join', protocol: protocol.PROTOCOL, name: 'Pending', publications: [] });
    mock.timers.tick(30000);
    assert(!pending.closed && pending.sent.some(message => message.type === 'presence'), 'Accepted member has no pending handshake timer');
    const noOpen = new Handshake(); noOpen.peer = 'no-open'; hub.accept(noOpen);
    mock.timers.tick(25000); assert(noOpen.closed, 'Unopened negotiation remains bounded');
    const noJoin = new Handshake(); noJoin.peer = 'no-join'; noJoin.open = true; hub.accept(noJoin);
    mock.timers.tick(10000); assert(noJoin.closed, 'Open channel without valid join expires');
    hub.close(false);
    const abandoned = new RoomCoordinator('none', []), dangling = new Handshake(); abandoned.accept(dangling); abandoned.close(false);
    assert(dangling.closed, 'Closing coordinator closes pending negotiations');
  } finally { mock.timers.reset(); }
  console.log('PASS: coordinator separates negotiation and join deadlines, bounds pending channels and clears accepted timers');
  const { observeRoomConnection } = await import(pathToFileURL(resolve(directory, 'connectionDiagnostics.mjs')));
  const diagnosticChannel = new EventEmitter();
  const diagnosticPeer = Object.assign(new EventTarget(), { iceConnectionState: 'new', connectionState: 'new', iceGatheringState: 'new' });
  diagnosticChannel.peerConnection = diagnosticPeer;
  const connectionLog = []; let diagnosticCurrent = true;
  observeRoomConnection(diagnosticChannel, () => diagnosticCurrent, message => connectionLog.push(message));
  const route = new Event('icecandidate');
  Object.defineProperty(route, 'candidate', { value: { type: 'srflx', address: '192.0.2.1', candidate: 'PRIVATE-SDP' } });
  diagnosticPeer.dispatchEvent(route);
  const iceError = new Event('icecandidateerror');
  Object.defineProperty(iceError, 'errorCode', { value: 701 });
  Object.defineProperty(iceError, 'url', { value: 'turn:PRIVATE-CREDENTIALS' });
  diagnosticPeer.dispatchEvent(iceError); diagnosticPeer.dispatchEvent(iceError);
  diagnosticPeer.iceGatheringState = 'complete'; diagnosticPeer.iceConnectionState = 'failed';
  diagnosticPeer.dispatchEvent(new Event('iceconnectionstatechange'));
  assert(connectionLog.some(line => line.includes('ICE failed')));
  assert(connectionLog.some(line => line.includes('públicas 1')));
  assert.equal(connectionLog.filter(line => line.includes('701')).length, 1);
  assert(!connectionLog.join('\n').match(/192\.0\.2|PRIVATE/), 'Diagnostic must not disclose candidates, IPs or credentials');
  const logLength = connectionLog.length;
  diagnosticCurrent = false; diagnosticPeer.iceConnectionState = 'connected';
  diagnosticPeer.dispatchEvent(new Event('iceconnectionstatechange'));
  assert.equal(connectionLog.length, logLength, 'Old connection cannot modify the next attempt');
  diagnosticChannel.emit('close'); diagnosticCurrent = true;
  diagnosticPeer.dispatchEvent(new Event('iceconnectionstatechange'));
  assert.equal(connectionLog.length, logLength, 'Closing removes transport listeners');
  assert.equal(diagnosticChannel.listenerCount('iceStateChanged'), 0);
  const relayedChannel = new EventEmitter(); const relayLog = [];
  relayedChannel.peerConnection = Object.assign(new EventTarget(), { connectionState: 'connected', iceConnectionState: 'connected', iceGatheringState: 'complete',
    async getStats() { return new Map([['pair', { type: 'candidate-pair', state: 'succeeded', nominated: true, localCandidateId: 'local', remoteCandidateId: 'remote' }],
      ['local', { candidateType: 'relay', address: 'PRIVATE-IP' }], ['remote', { candidateType: 'host' }]]); } });
  observeRoomConnection(relayedChannel, () => true, message => relayLog.push(message)); await wait();
  assert(relayLog.some(line => line.includes('Rota da entrada: retransmissão TURN')));
  assert(!relayLog.join('').includes('PRIVATE-IP')); relayedChannel.emit('close');
  console.log('PASS: room ICE failure is observable without IP/SDP/credentials, duplicated errors or stale callbacks');
  assert.equal(protocol.normalizeRoom(' https://example.test/watch.html?room=xnx-abcd '), 'XNX-ABCD');
  assert.equal(protocol.normalizeRoom('../../config'), '');
  assert.equal(protocol.parseClientMessage({ type: 'sharing', active: true, title: 'x', revision: NaN }), null);
  assert.equal(protocol.parseClientMessage({ type: 'join', name: 'x', protocol: 'old' }), null);
  assert.equal(protocol.parseServerMessage({ type: 'presence', participants: [{ peerId: 1 }] }), null);
  assert.equal(new URL(protocol.roomLink('https://example.test/sub/?old=1#foo', 'XNX-ABCD')).search, '?room=XNX-ABCD');
  assert.deepEqual(quality.fitWithin(3440, 1440, 1920, 1080), { width: 1920, height: 802 });
  assert.deepEqual(quality.fitWithin(800, 600, 1920, 1080), { width: 800, height: 600 });
  assert(quality.bitrateBudget(quality.DEFAULT_QUALITY, 4) < quality.bitrateBudget(quality.DEFAULT_QUALITY, 1));
  console.log('PASS: room validation, protocol validation, aspect ratio and upload budgeting');

  const { openCaptureSocket } = await import(pathToFileURL(resolve(directory, 'captureSocket.mjs')));
  const layout = await import(pathToFileURL(resolve(directory, 'stageLayout.mjs')));
  const preferences = await import(pathToFileURL(resolve(directory, 'stagePreferences.mjs')));
  const brokenLayout = preferences.parseStagePreferences('{');
  assert.equal(brokenLayout.mode, 'grid');
  const safeLayout = preferences.parseStagePreferences(JSON.stringify({ version: 1, mode: 'free', showLocal: false,
    privateName: 'DO NOT PERSIST', slots: [{ x: -4, y: 90, width: 2, height: .01, peerId: 'DO NOT PERSIST' }, { x: 'bad' }] }));
  assert.equal(safeLayout.slots.length, 1); assert.equal(safeLayout.slots[0].x, 0);
  assert.equal(safeLayout.slots[0].width, 1); assert(safeLayout.slots[0].y + safeLayout.slots[0].height <= 1);
  assert(!JSON.stringify(safeLayout).includes('DO NOT PERSIST'));
  const crowdedLayout = preferences.parseStagePreferences(JSON.stringify({ version: 1, slots: Array(60).fill({ x: 0, y: 0, width: .5, height: .5 }) }));
  assert.equal(crowdedLayout.slots.length, 32);
  assert.equal(preferences.readStagePreferences().mode, 'grid', 'Storage absence does not prevent using the room');
  console.log('PASS: anonymous saved layouts reject corrupt/versioned data, clamp geometry and bound slot count without requiring storage');
  assert.equal(preferences.parseStagePreferences(JSON.stringify({ version: 1, mode: 'free', snap: true })).snap, true);
  const snapped = layout.snapTransformRect({ x: .123, y: .22, width: .433, height: .427 }, .02, .02, 'move', .2, .15);
  assert(Math.abs(snapped.x - .15) < 1e-9 && Math.abs(snapped.y - .25) < 1e-9);
  const anchoredSnap = layout.snapTransformRect({ x: .123, y: .22, width: .433, height: .427 }, .02, .02, 'nw', .2, .15);
  assert(Math.abs(anchoredSnap.x + anchoredSnap.width - .556) < 1e-9 && Math.abs(anchoredSnap.y + anchoredSnap.height - .647) < 1e-9);
  const { SessionBenchmark, distribution } = await import(pathToFileURL(resolve(directory, 'sessionBenchmark.mjs')));
  let benchmarkClock = 0;
  const measurement = new SessionBenchmark(60, () => benchmarkClock), trackKey = { privateName: 'DO NOT EXPORT' };
  for (let i = 0; i < 600; i++) measurement.record(trackKey, 'incoming', { fps: i % 60, mbps: 4, width: 1920, height: 1080, health: { decodeMs: 2 } }, 'video/H264');
  measurement.record(trackKey, 'incoming', { fps: NaN, health: { droppedFrames: 2 } }, 'SECRET_SDP');
  benchmarkClock = 60000; measurement.record({}, 'outgoing', { fps: 120 });
  const measured = measurement.report();
  assert.equal(measured.active, false); assert.equal(measured.tracks.length, 1);
  assert.equal(measured.tracks[0].metrics.fps.samples, 512);
  assert.equal(measured.tracks[0].measuredDrops, 2); assert.equal(measured.tracks[0].measuredFreezes, null);
  assert.equal(measured.tracks[0].lastCodec, 'video/H264'); assert.equal(measured.measuredSeconds, 60);
  assert(!JSON.stringify(measured).includes('DO NOT EXPORT')); assert(!JSON.stringify(measured).includes('SECRET'));
  assert.deepEqual(distribution([1, 2, 3, 4]), { samples: 4, mean: 2.5, p50: 2, p95: 4, min: 1, max: 4 });
  const missingMetric = new SessionBenchmark(900, () => benchmarkClock);
  for (let i = 0; i < 300; i++) missingMetric.record({}, 'incoming', {});
  missingMetric.stop(); benchmarkClock += 900000;
  assert.equal(missingMetric.report().tracks.length, 256);
  assert.equal(missingMetric.report().tracks[0].metrics.fps, null);
  assert.equal(missingMetric.report().measuredSeconds, 0, 'Stop freezes measurement duration');
  const backgroundMeasure = new SessionBenchmark(60, () => benchmarkClock);
  backgroundMeasure.record({}, 'incoming', { fps: 5, arrivalFps: 60, activity: 'hidden' });
  assert.equal(backgroundMeasure.report().tracks[0].activitySamples.hidden, 1);
  assert.equal(backgroundMeasure.report().tracks[0].metrics.arrivalFps.mean, 60);
  assert.equal(backgroundMeasure.report().tracks[0].metrics.fps.mean, 5);
  console.log('PASS: timed RTP benchmark bounds tracks/samples, computes distributions, preserves unknown counters and excludes identities');
  assert.deepEqual(layout.constrainRect({ x: -1, y: 2, width: .5, height: .5 }), { x: 0, y: .5, width: .5, height: .5 });
  for (let index = 0; index < 32; index++) {
    const rect = layout.initialRect(index, 32);
    assert(rect.x >= 0 && rect.y >= 0 && rect.x + rect.width <= 1 && rect.y + rect.height <= 1);
  }
  const rect = { x: .25, y: .2, width: .5, height: .4 };
  for (const mode of ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'move']) {
    for (const dx of [-10, -.15, 0, .15, 10]) for (const dy of [-10, -.1, 0, .1, 10]) {
      const next = layout.transformRect(rect, dx, dy, mode, .2, .15);
      assert(next.x >= 0 && next.y >= 0 && next.width >= .2 - 1e-10 && next.height >= .15 - 1e-10);
      assert(next.x + next.width <= 1 + 1e-10 && next.y + next.height <= 1 + 1e-10);
      if (mode.includes('w')) assert(Math.abs(next.x + next.width - (rect.x + rect.width)) < 1e-10);
      if (mode.includes('n')) assert(Math.abs(next.y + next.height - (rect.y + rect.height)) < 1e-10);
    }
  }
  const { sampleRtp } = await import(pathToFileURL(resolve(directory, 'streamStats.mjs')));
  assert.equal(sampleRtp({ timestamp: 1000 }).reading.fps, undefined, 'Unsupported FPS must remain unknown');
  assert.equal(sampleRtp({ timestamp: 1000, framesDecoded: 0, framesPerSecond: 0 }).reading.fps, undefined, 'Startup is not a measured freeze');
  const rtpFirst = sampleRtp({ timestamp: 1000, framesDecoded: 10, bytesReceived: 1000 });
  const rtpSecond = sampleRtp({ timestamp: 3000, framesDecoded: 130, bytesReceived: 1001000, framesPerSecond: 0 }, rtpFirst.sample);
  assert.equal(rtpSecond.reading.fps, 60, 'Decoded counters override an erroneous instantaneous zero');
  assert.equal(rtpSecond.reading.mbps, 4);
  assert.equal(sampleRtp({ timestamp: 5000, framesDecoded: 130 }, { timestamp: 3000, frames: 130 }).reading.fps, 0, 'A measured stalled stream remains distinguishable');
  assert.equal(sampleRtp({ timestamp: 5000, framesDecoded: 1 }, rtpSecond.sample).reading.fps, undefined, 'Counter reset starts a new baseline');
  assert.equal(sampleRtp({ timestamp: 3000, framesDecoded: 130 }, rtpSecond.sample).reading.fps, undefined, 'Duplicate timestamp is not a measurement');
  assert.equal(sampleRtp({ timestamp: 20000, framesDecoded: 130 }, rtpSecond.sample).reading.fps, undefined, 'Old background-tab samples are not current FPS');
  assert.equal(sampleRtp({ timestamp: 1000, framesPerSecond: 29.9 }).reading.fps, 29.9);
  console.log('PASS: resizing from all eight edges stays bounded and anchored; missing/reset/stalled RTP counters are distinct');
  let attempts = 0; let failCount = 2; const sockets = [];
  class Socket {
    constructor() {
      attempts++; sockets.push(this); this.closed = false;
      queueMicrotask(() => { if (this.closed) return; if (attempts <= failCount) this.onerror?.(); else this.onopen?.(); });
    }
    close() { this.closed = true; }
  }
  globalThis.WebSocket = Socket;
  const ready = await openCaptureSocket('ws://fixture', new AbortController().signal, 1000, 5);
  assert.equal(attempts, 3); assert.equal(ready.closed, false);
  assert(sockets.slice(0, 2).every(socket => socket.closed)); ready.close();
  const cancelled = new AbortController(); cancelled.abort();
  await assert.rejects(openCaptureSocket('ws://fixture', cancelled.signal, 1000, 5), { name: 'AbortError' });
  assert.equal(attempts, 3, 'Already cancelled requests never create sockets');
  failCount = Infinity;
  const pending = new AbortController();
  const opening = openCaptureSocket('ws://fixture', pending.signal, 1000, 100);
  setTimeout(() => pending.abort(), 5);
  await assert.rejects(opening, { name: 'AbortError' });
  await assert.rejects(openCaptureSocket('ws://fixture', new AbortController().signal, 25, 5), /não respondeu/);
  assert(sockets.every(socket => socket.closed), 'Cancelled/expired attempts must not leak sockets');
  const beforeDeadWorker = attempts;
  await assert.rejects(openCaptureSocket('ws://fixture', new AbortController().signal, 1000, 5, async () => { throw new Error('stopped'); }), /processo auxiliar/);
  assert.equal(attempts, beforeDeadWorker, 'Exited worker fails before opening more sockets');
  let completeHealth;
  const lateHealth = new Promise(resolve => { completeHealth = resolve; });
  const cancelledHealth = new AbortController();
  const checkingWorker = openCaptureSocket('ws://fixture', cancelledHealth.signal, 1000, 5, () => lateHealth);
  cancelledHealth.abort(); await assert.rejects(checkingWorker, { name: 'AbortError' });
  completeHealth(); await wait();
  assert.equal(attempts, beforeDeadWorker, 'Late health reply cannot reconnect after cancel');
  let active = 0; let maxActive = 0; const applied = [];
  const sender = { track: { kind: 'video' }, getParameters() { return { encodings: [{}] }; },
    async setParameters(params) { active++; maxActive = Math.max(maxActive, active); await wait(); applied.push(params); active--; } };
  const pc = { getSenders: () => [sender] };
  await Promise.all([
    quality.tuneConnection(pc, { ...quality.DEFAULT_QUALITY, fps: 60 }, 1),
    quality.tuneConnection(pc, { ...quality.DEFAULT_QUALITY, fps: 120, delivery: 'adaptive' }, 2),
  ]);
  assert.equal(maxActive, 1, 'Concurrent retunes must not reuse stale sender transactions');
  assert.equal(applied[0].degradationPreference, 'maintain-resolution');
  assert.equal(applied[0].encodings[0].scaleResolutionDownBy, 1);
  assert.equal(applied[0].encodings[0].maxFramerate, 60);
  assert.equal(applied[1].degradationPreference, 'balanced');
  assert.equal(applied[1].encodings[0].maxFramerate, 120);
  console.log('PASS: worker readiness retry, cancellation, timeout, layout bounds and serialized quality preservation');

  const { startCapture, browserDisplayOptions } = await import(pathToFileURL(resolve(directory, 'capture.mjs')));
  const browserOptions = { source: 'browser', audio: 'system', quality: quality.DEFAULT_QUALITY };
  const protectedCapture = browserDisplayOptions(browserOptions, true);
  assert.equal(protectedCapture.audio.restrictOwnAudio, true);
  assert.equal(protectedCapture.windowAudio, 'window');
  assert.equal(protectedCapture.systemAudio, 'include');
  assert.equal('restrictOwnAudio' in browserDisplayOptions(browserOptions, false).audio, false);
  const silentCapture = browserDisplayOptions({ ...browserOptions, audio: 'none' }, true);
  assert.equal(silentCapture.audio, false);
  assert.equal(silentCapture.windowAudio, undefined);
  console.log('PASS: browser requests own-audio restriction when supported and prefers isolated window audio');
  const video = { kind: 'video', readyState: 'live', stop() { this.readyState = 'ended'; }, addEventListener() {} };
  const media = { getTracks: () => [video], getVideoTracks: () => [video], getAudioTracks: () => [] };
  let videoWindow, audioPid, released = 0, owned = false;
  globalThis.window = { chrome: { webview: { postMessage() {}, hostObjects: { api: {
    GetCaptureToken: async () => 'a'.repeat(64),
    TryBeginCapture: async () => { owned = true; return true; }, EndCapture: async () => { released++; owned = false; },
    BeginNativeCapture: async (_, hwnd) => { videoWindow = hwnd; return true; },
    BeginCaptureAudio: async (_, pid) => { audioPid = pid; return false; },
    StopCaptureAudio: async () => {},
    GetCaptureState: async () => JSON.stringify({ phase: owned ? 'active' : 'idle', video: 'ready', audio: 'idle' }),
  } } } } };
  globalThis.document = { createElement: () => ({ getContext: () => ({ drawImage() {} }), captureStream: () => media }) };
  globalThis.createImageBitmap = async () => ({ width: 1280, height: 720, close() {} });
  globalThis.WebSocket = class extends Socket {
    constructor() {
      super();
      setTimeout(() => { this.onopen?.(); setTimeout(() => this.onmessage?.({ data: new ArrayBuffer(4) }), 5); }, 1);
    }
  };
  // Disable the earlier refusal fixture; this worker provides one synthetic video frame.
  failCount = 0;
  const native = await startCapture({ source: 'window', process: { Hwnd: 111, Pid: 11 },
    audioProcess: { Hwnd: 222, Pid: 22 }, audio: 'process', quality: quality.DEFAULT_QUALITY }, new AbortController().signal, () => {});
  assert.equal(videoWindow, 111); assert.equal(audioPid, 22);
  await native.stop(); assert.equal(released, 1);
  await assert.rejects(startCapture({ source: 'monitor', audio: 'process', quality: quality.DEFAULT_QUALITY }, new AbortController().signal, () => {}), /Selecione/);
  console.log('PASS: independent native video HWND/audio PID, cleanup and missing-audio validation');

  class Data extends EventEmitter {
    constructor(peer) { super(); this.peer = peer; this.open = false; }
    send(message) { queueMicrotask(() => { if (this.partner?.open) this.partner.emit('data', structuredClone(message)); }); }
    close() { if (!this.open) return; this.open = false; this.emit('close'); if (this.partner?.open) this.partner.close(); }
  }
  class Media extends EventEmitter {
    constructor(peer, stream) {
      super(); this.peer = peer; this.stream = stream; this.closed = false;
      this.peerConnection = { connectionState: 'connected', addEventListener() {}, getSenders() { return []; } };
    }
    answer(_, options) { this.answerCalls = (this.answerCalls || 0) + 1; this.answerOptions = options; queueMicrotask(() => { if (!this.closed) this.emit('stream', this.stream); }); }
    close() { if (this.closed) return; this.closed = true; this.emit('close'); this.partner?.close(); }
  }
  const network = new Map(); let sequence = 0;
  let failHubOnce = false;
  let connectionDelay = 0; let connectCount = 0;
  class FakePeer extends EventEmitter {
    constructor(id, options = {}) {
      super(); this.options = options; this.id = id || `participant-${++sequence}`; this.destroyed = false; this.disconnected = false; this.connections = [];
      if (failHubOnce && this.id.startsWith('xennex-v3-')) { failHubOnce = false; queueMicrotask(() => this.emit('error', { type: 'network', message: 'temporary hub failure' })); return; }
      if (network.has(this.id)) { queueMicrotask(() => this.emit('error', { type: 'unavailable-id', message: 'duplicate' })); return; }
      network.set(this.id, this); queueMicrotask(() => { if (!this.destroyed) this.emit('open', this.id); });
    }
    connect(id) {
      connectCount++; const delay = connectionDelay;
      const data = new Data(id); this.connections.push(data); const target = network.get(id);
      const open = () => {
        if (!target) { this.emit('error', { type: 'peer-unavailable', message: 'missing' }); return; }
        const remote = new Data(this.id); target.connections.push(remote); remote.partner = data; data.partner = remote;
        target.emit('connection', remote); data.open = remote.open = true; remote.emit('open'); data.emit('open');
      };
      if (delay) setTimeout(open, delay); else queueMicrotask(open);
      return data;
    }
    call(id, stream, options) {
      const call = new Media(id, stream); this.connections.push(call); const target = network.get(id);
      queueMicrotask(() => {
        if (!target) return;
        const remote = new Media(this.id, stream); remote.metadata = options.metadata; target.connections.push(remote);
        call.partner = remote; remote.partner = call; target.emit('call', remote);
      }); return call;
    }
    reconnect() { this.disconnected = false; queueMicrotask(() => this.emit('open', this.id)); }
    destroy() { if (this.destroyed) return; this.destroyed = true; if (network.get(this.id) === this) network.delete(this.id); this.connections.forEach(c => c.close()); this.emit('close'); }
  }
  const create = () => { const client = new RoomClient((id, options) => new FakePeer(id, options)); clients.push(client); return client; };
  const until = async predicate => { const deadline = Date.now() + 14000; while (!predicate()) { if (Date.now() > deadline) throw new Error('Timed out'); await wait(); } };
  const missing = create(); missing.start('XNX-NOT-CREATED', 'First visitor', false);
  await until(() => missing.getSnapshot().phase === 'error');
  assert.match(missing.getSnapshot().message, /não foi encontrada/);
  assert.match(missing.getSnapshot().message, /Criar sala/);
  assert.equal(missing.getSnapshot().entry.failure, 'missing-room');
  assert(!entryReport(missing.getSnapshot().entry, 'error', false).includes('XNX-NOT-CREATED'), 'Reports exclude room codes');
  assert(!network.has(protocol.roomPeerId('XNX-NOT-CREATED')), 'Join must not silently create a room');
  const slowHost = create(); slowHost.start('XNX-SLOW', 'Slow host', true);
  await until(() => slowHost.getSnapshot().phase === 'connected');
  connectionDelay = 6500; const before = connectCount;
  const slowGuest = create(); slowGuest.start('XNX-SLOW', 'Slow guest', false);
  await until(() => slowGuest.getSnapshot().phase === 'connected');
  assert.equal(connectCount - before, 1, 'Do not replace the pending handshake after five seconds');
  connectionDelay = 0; slowGuest.leave(); slowHost.leave();
  console.log('PASS: missing room gives actionable error; 6.5-second connection completes without restart');
  failHubOnce = true;
  const retryHost = create(); retryHost.start('XNX-RETRY-HUB', 'Retry', true);
  await until(() => retryHost.getSnapshot().phase === 'connected');
  assert(retryHost.getSnapshot().diagnostics.some(line => line.includes('Erro da coordenação: network')));
  retryHost.leave();
  console.log('PASS: creation recovers from transient coordinator registration failure');
  const host = create(); const viewer = create(); const guest = create();
  host.start('XNX-TEST', 'Host', true); await until(() => host.getSnapshot().phase === 'connected');
  viewer.start('XNX-TEST', 'Viewer', false); guest.start('XNX-TEST', 'Guest', false); await wait();
  assert.equal(viewer.getSnapshot().phase, 'connected');
  await until(() => viewer.getSnapshot().workspace.snapshot && !viewer.getSnapshot().workspace.synchronizing);
  assert.deepEqual(await viewer.workspace.dispatch({ kind: 'chat', text: 'Session tools connected' }), { ok: true });
  assert.deepEqual(await guest.workspace.dispatch({ kind: 'note', text: 'Keep this shared note', baseRevision: 0 }), { ok: true });
  assert.equal(host.getSnapshot().workspace.snapshot.messages[0].author, viewer.getSnapshot().selfId);
  assert.equal(host.getSnapshot().workspace.snapshot.note.text, 'Keep this shared note');
  viewer.setName('Alice'); await wait();
  assert.equal(host.getSnapshot().participants.find(p => p.peerId === viewer.getSnapshot().selfId).name, 'Alice');
  const spoof = network.get(viewer.getSnapshot().selfId).connections.find(c => c instanceof Data && c.open);
  spoof.send({ type: 'name', name: 'Spoofed', peerId: host.getSnapshot().selfId }); await wait();
  assert.equal(host.getSnapshot().participants.find(p => p.peerId === host.getSnapshot().selfId).name, 'Host');
  const publication = (id, kind = 'screen') => ({ id, title: id, kind, stream: { label: id }, quality: quality.DEFAULT_QUALITY });
  const first = publication('guest-screen-1'); const second = publication('guest-screen-2'); const camera = publication('guest-camera', 'camera');
  [first, second, camera].forEach(p => guest.addLocal(p)); host.addLocal(publication('host-screen')); viewer.addLocal(publication('viewer-screen')); await wait();
  assert.equal(viewer.getSnapshot().streams.size, 0, 'No automatic subscriptions');
  viewer.setWatching([first.id, camera.id]); host.setWatching([second.id]); guest.setWatching(['viewer-screen']); await wait();
  assert.equal(viewer.getSnapshot().streams.get(first.id), first.stream);
  assert.equal(viewer.getSnapshot().streams.get(camera.id), camera.stream);
  assert(!viewer.getSnapshot().streams.has(second.id));
  guest.removeLocal(first.id); await wait(); assert(!viewer.getSnapshot().streams.has(first.id));
  assert.equal(viewer.getSnapshot().streams.get(camera.id), camera.stream);
  console.log('PASS: simultaneous publishers, two screens plus camera, independent selection and stop');
  const relayLease = { iceServers: [{ urls: ['turns:turn.cloudflare.com:443?transport=tcp'], username: 'fixture', credential: 'short-lived-fixture' }], expiresAt: Date.now() + 600000 };
  const fallbackGuest = create();
  const unchangedMedia = viewer.getSnapshot().streams.get(camera.id);
  const unchangedViewerId = viewer.getSnapshot().selfId;
  const unchangedCoordinator = viewer.getSnapshot().coordinator;
  assert.throws(() => viewer.start('XNX-TEST', 'Viewer', false, relayLease), /antes de entrar/);
  assert.equal(viewer.getSnapshot().selfId, unchangedViewerId);
  fallbackGuest.start('XNX-TEST', 'Fallback guest', false, relayLease);
  await until(() => fallbackGuest.getSnapshot().phase === 'connected');
  const fallbackPeer = network.get(fallbackGuest.getSnapshot().selfId);
  assert.equal(fallbackGuest.getSnapshot().transport, 'alternative');
  assert.equal(fallbackPeer.options.config.iceTransportPolicy, 'all');
  assert(fallbackPeer.options.config.iceServers.some(server => server.credential === 'short-lived-fixture'));
  assert.equal(network.get(unchangedViewerId).options.config, undefined, 'Other participants retain their original ICE settings');
  assert.equal(viewer.getSnapshot().streams.get(camera.id), unchangedMedia);
  assert.equal(viewer.getSnapshot().coordinator, unchangedCoordinator);
  const alternativeChannel = fallbackPeer.connections.find(connection => connection instanceof Data && connection.open);
  let renewedConfigurations = 0;
  alternativeChannel.peerConnection = { connectionState: 'connected', getConfiguration: () => ({ iceServers: [] }),
    setConfiguration(config) { renewedConfigurations++; assert(config.iceServers.some(server => server.credential === 'renewed-fixture')); } };
  assert(fallbackGuest.renewTurn({ ...relayLease, iceServers: [{ ...relayLease.iceServers[0], credential: 'renewed-fixture' }] }));
  assert.equal(renewedConfigurations, 1);
  assert.equal(fallbackPeer.destroyed, false, 'Renewal must not restart participant or media');
  assert.equal(viewer.getSnapshot().streams.get(camera.id), unchangedMedia);
  fallbackGuest.leave(); fallbackGuest.start('XNX-TEST', 'Direct again', false);
  await until(() => fallbackGuest.getSnapshot().phase === 'connected');
  assert.equal(fallbackGuest.getSnapshot().transport, 'direct');
  assert.equal(network.get(fallbackGuest.getSnapshot().selfId).options.config, undefined, 'Direct retry forgets TURN credentials');
  fallbackGuest.leave(); await wait();
  const invalidFallback = create();
  assert.throws(() => invalidFallback.start('XNX-TEST', 'Expired', false, { ...relayLease, expiresAt: 0 }), /vencidas/);
  assert.equal(invalidFallback.getSnapshot().phase, 'idle');
  console.log('PASS: optional TURN belongs to one participant; active peers/media/coordinator survive and direct retry forgets credentials');
  for (let i = 0; i < 9; i++) { const c = create(); c.start('XNX-TEST', `Friend ${i}`, false); }
  await until(() => host.getSnapshot().participants.length === 12);
  const collision = create(); collision.start('XNX-TEST', 'Collision', true); await wait(); assert.equal(collision.getSnapshot().phase, 'error');
  const originalCoordinator = host.getSnapshot().selfId; host.leave();
  await until(() => viewer.getSnapshot().phase === 'connected' && viewer.getSnapshot().coordinator !== originalCoordinator);
  assert.equal(viewer.getSnapshot().streams.get(camera.id), camera.stream, 'Media survives coordinator departure');
  await until(() => viewer.getSnapshot().participants.length === 11);
  const newcomer = create(); newcomer.start('XNX-TEST', 'New after migration', false);
  await until(() => newcomer.getSnapshot().phase === 'connected');
  await until(() => newcomer.getSnapshot().workspace.snapshot && !newcomer.getSnapshot().workspace.synchronizing);
  assert.equal(newcomer.getSnapshot().workspace.snapshot.note.text, 'Keep this shared note');
  assert.equal(newcomer.getSnapshot().workspace.snapshot.messages[0].text, 'Session tools connected');
  newcomer.setWatching([camera.id]); await until(() => newcomer.getSnapshot().streams.get(camera.id) === camera.stream);
  // Abrupt coordinator loss, without migrate notification (like a crashed process).
  const crashedId = viewer.getSnapshot().coordinator;
  const crashedClient = clients.find(c => c.getSnapshot().selfId === crashedId);
  network.get(protocol.roomPeerId('XNX-TEST')).destroy();
  network.get(crashedId).destroy();
  assert.equal(crashedClient.getSnapshot().phase, 'error');
  await until(() => newcomer.getSnapshot().phase === 'connected' && newcomer.getSnapshot().coordinator !== crashedId);
  assert.equal(newcomer.getSnapshot().streams.get(camera.id), camera.stream);
  await until(() => newcomer.getSnapshot().workspace.snapshot && !newcomer.getSnapshot().workspace.synchronizing);
  assert.equal(newcomer.getSnapshot().workspace.snapshot.note.text, 'Keep this shared note');
  console.log('PASS: 12 participants, graceful migration, late join and abrupt coordinator crash');
  assert.equal(quality.captureFps(0), 120); assert.equal(quality.captureFps(999), 120); assert.equal(quality.captureFps(1), 1);
  assert(quality.bitrateBudget({ ...quality.DEFAULT_QUALITY, fps: 0 }, 1) > 150000);
  const capacityHost = create(); capacityHost.start('XNX-CAPACITY', 'Capacity', true);
  await until(() => capacityHost.getSnapshot().phase === 'connected');
  for (let i = 1; i < protocol.MAX_PARTICIPANTS; i++) { const c = create(); c.start('XNX-CAPACITY', `Member ${i}`, false); }
  await until(() => capacityHost.getSnapshot().participants.length === protocol.MAX_PARTICIPANTS);
  const overflow = create(); overflow.start('XNX-CAPACITY', 'Overflow', false); await until(() => overflow.getSnapshot().phase === 'error');
  for (let i = 0; i < protocol.MAX_LOCAL_STREAMS; i++) capacityHost.addLocal(publication(`capacity-${i}`));
  assert.throws(() => capacityHost.addLocal(publication('extra-source')), /Limite/);
  assert(quality.bitrateBudget({ ...quality.DEFAULT_QUALITY, uploadMbps: 1 }, 32) * 32 <= 850000);
  console.log('PASS: 32-member admission limit, six sources and shared upload ceiling');
  const codecHost = create(), codecA = create(), codecB = create();
  codecHost.start('XNX-CODECS', 'Codec host', true); await until(() => codecHost.getSnapshot().phase === 'connected');
  codecA.start('XNX-CODECS', 'A', false); codecB.start('XNX-CODECS', 'B', false);
  await until(() => codecHost.getSnapshot().participants.length === 3);
  const codecPublication = publication('codec-fixture'); codecHost.addLocal(codecPublication);
  await until(() => codecA.getSnapshot().participants.some(p => p.publications.some(s => s.id === codecPublication.id)));
  codecA.setWatching([codecPublication.id]); codecB.setWatching([codecPublication.id]);
  await until(() => codecA.getSnapshot().streams.has(codecPublication.id) && codecB.getSnapshot().streams.has(codecPublication.id));
  const callsFor = client => network.get(client.getSnapshot().selfId).connections.filter(c => c instanceof Media && !c.closed);
  const aBefore = callsFor(codecA)[0], bBefore = callsFor(codecB)[0];
  codecA.setReceivingCodec('compatibility');
  await until(() => callsFor(codecA).some(c => c !== aBefore) && codecA.getSnapshot().streams.has(codecPublication.id));
  assert(aBefore.closed); assert.equal(callsFor(codecB)[0], bBefore); assert(!bBefore.closed);
  assert.equal(codecA.receivingCodec, 'compatibility'); assert.equal(codecB.receivingCodec, 'auto');
  assert.equal(codecHost.getSnapshot().phase, 'connected');
  console.log('PASS: receiver codec preference reconnects only its own subscriptions, preserving other viewers and host');
  const receiverDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'RTCRtpReceiver'), navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  try {
    let finishDecode;
    Object.defineProperty(globalThis, 'RTCRtpReceiver', { configurable: true, value: { getCapabilities: () => ({ codecs: [{ mimeType: 'video/VP8' }] }) } });
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaCapabilities: { decodingInfo: () => new Promise(resolve => { finishDecode = resolve; }) } } });
    const pending = publication('late-codec-fixture'); pending.quality = { ...pending.quality, fps: 29 };
    codecHost.addLocal(pending);
    await until(() => codecA.getSnapshot().participants.some(p => p.publications.some(s => s.id === pending.id)));
    codecA.setWatching([pending.id]);
    await until(() => !!finishDecode);
    const waiting = callsFor(codecA).find(c => c.metadata.publication === pending.id);
    assert(waiting); assert.equal(waiting.answerCalls, undefined);
    codecA.setWatching([]); finishDecode({ supported: true, smooth: true, powerEfficient: true }); await wait();
    assert(waiting.closed); assert.equal(waiting.answerCalls, undefined); assert(!codecA.getSnapshot().streams.has(pending.id));
    console.log('PASS: late capability probe cannot answer a cancelled incoming call');
  } finally {
    if (receiverDescriptor) Object.defineProperty(globalThis, 'RTCRtpReceiver', receiverDescriptor); else delete globalThis.RTCRtpReceiver;
    if (navigatorDescriptor) Object.defineProperty(globalThis, 'navigator', navigatorDescriptor); else delete globalThis.navigator;
  }
  for (const c of clients) c.leave();
  await new Promise(resolve => setTimeout(resolve, 250));
  assert.equal(network.size, 0, 'Last participant releases room code and all peers');
  console.log('PASS: FPS automatic/120 and room cleanup after last participant');
} finally {
  clients.forEach(client => client.leave());
  await rm(directory, { recursive: true, force: true });
}
