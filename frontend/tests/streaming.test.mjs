import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const directory = await mkdtemp(resolve('node_modules/.xennex-stream-tests-'));
const clients = [];
const wait = () => new Promise(resolve => setTimeout(resolve, 15));
try {
  for (const name of ['protocol', 'quality', 'RoomCoordinator', 'RoomClient']) {
    let source = await readFile(`src/features/stream/${name}.ts`, 'utf8');
    if (name === 'RoomClient') source = source.replace(/import .*? from 'peerjs';/, 'const Peer = class {};').replace("import { peerOptions } from './peerConfig';", 'const peerOptions = () => ({});');
    source = source.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'");
    await writeFile(resolve(directory, `${name}.mjs`), ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  }
  const protocol = await import(pathToFileURL(resolve(directory, 'protocol.mjs')));
  const quality = await import(pathToFileURL(resolve(directory, 'quality.mjs')));
  const { RoomClient } = await import(pathToFileURL(resolve(directory, 'RoomClient.mjs')));
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
    answer() { queueMicrotask(() => { if (!this.closed) this.emit('stream', this.stream); }); }
    close() { if (this.closed) return; this.closed = true; this.emit('close'); this.partner?.close(); }
  }
  const network = new Map(); let sequence = 0;
  let failHubOnce = false;
  let connectionDelay = 0; let connectCount = 0;
  class FakePeer extends EventEmitter {
    constructor(id) {
      super(); this.id = id || `participant-${++sequence}`; this.destroyed = false; this.disconnected = false; this.connections = [];
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
  const create = () => { const client = new RoomClient(id => new FakePeer(id)); clients.push(client); return client; };
  const until = async predicate => { const deadline = Date.now() + 14000; while (!predicate()) { if (Date.now() > deadline) throw new Error('Timed out'); await wait(); } };
  const missing = create(); missing.start('XNX-NOT-CREATED', 'First visitor', false);
  await until(() => missing.getSnapshot().phase === 'error');
  assert.match(missing.getSnapshot().message, /não foi encontrada/);
  assert.match(missing.getSnapshot().message, /Criar sala/);
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
  for (let i = 0; i < 9; i++) { const c = create(); c.start('XNX-TEST', `Friend ${i}`, false); }
  await until(() => host.getSnapshot().participants.length === 12);
  const collision = create(); collision.start('XNX-TEST', 'Collision', true); await wait(); assert.equal(collision.getSnapshot().phase, 'error');
  const originalCoordinator = host.getSnapshot().selfId; host.leave();
  await until(() => viewer.getSnapshot().phase === 'connected' && viewer.getSnapshot().coordinator !== originalCoordinator);
  assert.equal(viewer.getSnapshot().streams.get(camera.id), camera.stream, 'Media survives coordinator departure');
  await until(() => viewer.getSnapshot().participants.length === 11);
  const newcomer = create(); newcomer.start('XNX-TEST', 'New after migration', false);
  await until(() => newcomer.getSnapshot().phase === 'connected');
  newcomer.setWatching([camera.id]); await wait(); assert.equal(newcomer.getSnapshot().streams.get(camera.id), camera.stream);
  // Abrupt coordinator loss, without migrate notification (like a crashed process).
  const crashedId = viewer.getSnapshot().coordinator;
  const crashedClient = clients.find(c => c.getSnapshot().selfId === crashedId);
  network.get(protocol.roomPeerId('XNX-TEST')).destroy();
  network.get(crashedId).destroy();
  assert.equal(crashedClient.getSnapshot().phase, 'error');
  await until(() => newcomer.getSnapshot().phase === 'connected' && newcomer.getSnapshot().coordinator !== crashedId);
  assert.equal(newcomer.getSnapshot().streams.get(camera.id), camera.stream);
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
  for (const c of clients) c.leave();
  await new Promise(resolve => setTimeout(resolve, 250));
  assert.equal(network.size, 0, 'Last participant releases room code and all peers');
  console.log('PASS: FPS automatic/120 and room cleanup after last participant');
} finally {
  clients.forEach(client => client.leave());
  await rm(directory, { recursive: true, force: true });
}
