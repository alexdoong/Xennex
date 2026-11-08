import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mock } from 'node:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const directory = await mkdtemp(resolve('node_modules/.room-workspace-'));
const coordinators = [];
const clients = [];
try {
  for (const name of ['workspaceProtocol', 'protocol', 'RoomWorkspaceState', 'RoomWorkspaceClient', 'RoomCoordinator']) {
    const source = (await readFile(`src/features/stream/${name}.ts`, 'utf8')).replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'");
    await writeFile(resolve(directory, `${name}.mjs`), ts.transpileModule(source, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
    }).outputText);
  }
  const { PROTOCOL, parseClientMessage, parseServerMessage } = await import(pathToFileURL(resolve(directory, 'protocol.mjs')));
  const { WORKSPACE_EXTENSION, parseWorkspaceSnapshot, parseWorkspaceAction } = await import(pathToFileURL(resolve(directory, 'workspaceProtocol.mjs')));
  const { RoomWorkspaceClient } = await import(pathToFileURL(resolve(directory, 'RoomWorkspaceClient.mjs')));
  const { RoomWorkspaceState } = await import(pathToFileURL(resolve(directory, 'RoomWorkspaceState.mjs')));
  const { RoomCoordinator } = await import(pathToFileURL(resolve(directory, 'RoomCoordinator.mjs')));
  class Channel extends EventEmitter {
    open = true; sent = [];
    constructor(peer, receive = () => {}) { super(); this.peer = peer; this.receive = receive; }
    send(value) { this.sent.push(value); this.receive(structuredClone(value)); }
    close() { if (!this.open) return; this.open = false; this.emit('close'); }
  }
  const createHub = seed => { const hub = new RoomCoordinator('owner', [], seed); coordinators.push(hub); return hub; };
  const join = (hub, peerId, supports = true) => {
    let view;
    const client = new RoomWorkspaceClient(request => { channel.emit('data', structuredClone(request)); return channel.open; }, state => { view = state; });
    clients.push(client);
    const channel = new Channel(peerId, value => {
      const message = parseServerMessage(value);
      if (message?.type === 'presence') client.capability(!!message.extensions?.includes(WORKSPACE_EXTENSION));
      else if (message?.type.startsWith('workspace-')) client.receive(message);
    });
    hub.accept(channel);
    channel.emit('data', { type: 'join', protocol: PROTOCOL, name: peerId, publications: [], ...(supports ? { extensions: [WORKSPACE_EXTENSION] } : {}) });
    return { client, channel, get view() { return view; } };
  };
  const hub = createHub(), owner = join(hub, 'owner'), guest = join(hub, 'guest');
  assert(owner.view.available && guest.view.snapshot);
  assert.deepEqual(await owner.client.dispatch({ kind: 'chat', text: '<script>literal text</script>' }), { ok: true });
  assert.equal(guest.view.snapshot.messages[0].author, 'owner');
  assert.equal(guest.view.snapshot.messages[0].text, '<script>literal text</script>');
  const baseRevision = guest.view.snapshot.note.revision;
  await owner.client.dispatch({ kind: 'note', text: 'Shared draft', baseRevision });
  assert.equal(guest.view.snapshot.note.text, 'Shared draft');
  assert.deepEqual(await guest.client.dispatch({ kind: 'note', text: 'Outdated overwrite', baseRevision }), { ok: false, reason: 'conflict' });
  assert.equal(owner.view.snapshot.note.text, 'Shared draft');
  await guest.client.dispatch({ kind: 'task-add', id: 'task-1', title: 'Check the scene' });
  await owner.client.dispatch({ kind: 'task-set', id: 'task-1', done: true });
  assert.deepEqual(guest.view.snapshot.tasks, [{ id: 'task-1', title: 'Check the scene', done: true }]);
  const late = join(hub, 'late');
  assert.deepEqual(late.view.snapshot, owner.view.snapshot);
  await late.client.dispatch({ kind: 'task-remove', id: 'task-1' });
  assert.equal(owner.view.snapshot.tasks.length, 0);
  console.log('PASS: two clients share chat/notes/tasks through the real coordinator; stale edits reject; late join restores bounded state');

  const request = { type: 'workspace-operation', id: 'repeat-1', epoch: owner.view.snapshot.epoch, action: { kind: 'chat', text: 'One message' }, author: 'spoofed', name: 'spoofed' };
  guest.channel.emit('data', request); guest.channel.emit('data', request);
  assert.equal(owner.view.snapshot.messages.filter(message => message.text === 'One message').length, 1);
  assert.equal(owner.view.snapshot.messages.at(-1).author, 'guest');
  const revision = owner.view.snapshot.revision;
  const legacy = join(hub, 'legacy', false);
  legacy.channel.emit('data', { ...request, id: 'legacy-attack' });
  assert.equal(owner.view.snapshot.revision, revision);
  assert(!legacy.channel.sent.some(message => message.type.startsWith('workspace-')));
  const snapshots = guest.channel.sent.filter(message => message.type === 'workspace-snapshot').length;
  guest.channel.emit('data', { type: 'join', protocol: PROTOCOL, name: 'renamed', publications: [], extensions: [WORKSPACE_EXTENSION] });
  assert.equal(guest.channel.sent.filter(message => message.type === 'workspace-snapshot').length, snapshots);
  const displaced = guest.channel;
  const replacement = join(hub, 'guest');
  displaced.emit('data', { ...request, id: 'displaced-attack' });
  assert.equal(replacement.view.snapshot.revision, revision);
  console.log('PASS: operations use admitted connection identity, deduplicate, reject legacy/unbound senders and ignore repeated join on same channel');

  const migrated = createHub(owner.view.snapshot), successor = join(migrated, 'owner');
  assert.notEqual(successor.view.snapshot.epoch, owner.view.snapshot.epoch);
  assert.deepEqual(successor.view.snapshot.messages, owner.view.snapshot.messages);
  assert.equal(successor.view.snapshot.note.text, 'Shared draft');
  successor.channel.emit('data', { ...request, id: 'old-epoch' });
  assert.equal(successor.channel.sent.at(-1).result.reason, 'conflict');
  owner.client.reset(); assert.equal(owner.view.snapshot, null);
  console.log('PASS: coordinator migration seeds accepted replica into a fresh epoch; leaving clears session content');

  assert.equal(parseWorkspaceAction({ kind: 'chat', text: 'x'.repeat(1001) }), null);
  assert.equal(parseClientMessage({ ...request, action: { kind: 'execute', command: 'anything' } }), null);
  assert.equal(parseWorkspaceSnapshot({ ...successor.view.snapshot, messages: Array(21).fill(successor.view.snapshot.messages[0]) }), null);
  assert.equal(parseServerMessage({ type: 'workspace-event', epoch: 'a', revision: NaN, change: { kind: 'chat', entry: {} } }), null);
  let now = 10000;
  const limits = new RoomWorkspaceState(undefined, () => now);
  const epoch = limits.snapshot().snapshot.epoch;
  for (let index = 0; index < 12; index++) assert(limits.handle({ peerId: 'p', name: 'P' }, { ...request, id: `op-${index}`, epoch }).event);
  assert.equal(limits.handle({ peerId: 'p', name: 'P' }, { ...request, id: 'overflow', epoch }).direct[0].result.reason, 'limited');
  now += 10001;
  assert(limits.handle({ peerId: 'p', name: 'P' }, { ...request, id: 'recovered', epoch }).event);
  const exported = limits.snapshot(); exported.snapshot.messages.length = 0;
  assert(limits.snapshot().snapshot.messages.length > 0);
  console.log('PASS: payloads, rate limits and snapshots bounded; snapshots cannot mutate coordinator-owned state');

  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const client = new RoomWorkspaceClient(() => true, () => {}); clients.push(client);
    assert.deepEqual(await client.dispatch({ kind: 'chat', text: 'No capability' }), { ok: false, reason: 'unavailable' });
    client.capability(true); client.receive(limits.snapshot());
    const waiting = client.dispatch({ kind: 'chat', text: 'No ack' });
    mock.timers.tick(8001); assert.deepEqual(await waiting, { ok: false, reason: 'timeout' });
    const canceled = client.dispatch({ kind: 'chat', text: 'Cancel' });
    client.disconnect(); assert.deepEqual(await canceled, { ok: false, reason: 'unavailable' });
  } finally { mock.timers.reset(); }
  console.log('PASS: missing capability, timeout and disconnect settle operations without touching media');
} finally {
  clients.forEach(client => client.reset());
  coordinators.forEach(hub => hub.close(false));
  await rm(directory, { recursive: true, force: true });
}
