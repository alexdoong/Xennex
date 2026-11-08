import { Peer, type DataConnection, type MediaConnection, type PeerJSOption } from 'peerjs';
import { HAS_TURN, peerOptions } from './peerConfig';
import { observeRoomConnection } from './connectionDiagnostics';
import { EntryDiagnostics, type EntryDiagnostic, type EntryFailure } from './entryDiagnostics';
import { parseTurnLease, type TurnLease } from './turnFallback';
import { tuneConnection, type Quality } from './quality';
import { probeCodecs, codecTransform, qualityHint, codecMode, type CodecMode } from './streamCapabilities';
import { RoomCoordinator, ROOM_NEGOTIATION_TIMEOUT_MS, ROOM_JOIN_TIMEOUT_MS } from './RoomCoordinator';
import { RoomWorkspaceClient, emptyWorkspaceView, type WorkspaceView } from './RoomWorkspaceClient';
import { WORKSPACE_EXTENSION } from './workspaceProtocol';
import { PROTOCOL, MAX_LOCAL_STREAMS, MAX_WATCHING, normalizeRoom, roomPeerId, displayName,
  parseServerMessage, type Participant, type Publication, type RoomPhase, type ClientMessage } from './protocol';

export interface LocalPublication extends Publication { stream: MediaStream; quality: Quality }
export interface RoomSnapshot {
  workspace: WorkspaceView;
  phase: RoomPhase; room: string; selfId: string; isHost: boolean; coordinator: string; message: string;
  transport: 'direct' | 'alternative'; turnExpiresAt: number; entry: EntryDiagnostic | null;
  diagnostics: string[]; participants: Participant[]; streams: ReadonlyMap<string, MediaStream>; watching: string[];
}
export type PeerFactory = (id: string | undefined, options: PeerJSOption) => Peer;
const makePeer: PeerFactory = (id, options) => id ? new Peer(id, options) : new Peer(options);
const emptySnapshot = (): RoomSnapshot => ({ workspace: emptyWorkspaceView(), phase: 'idle', room: '', selfId: '', isHost: false, coordinator: '', message: '', transport: 'direct', turnExpiresAt: 0, entry: null, diagnostics: [], participants: [], streams: new Map(), watching: [] });
export class RoomClient {
  readonly workspace = new RoomWorkspaceClient(message => this.send(message), workspace => this.update({ workspace }));
  private snapshot = emptySnapshot();
  private listeners = new Set<() => void>();
  private peer?: Peer;
  private hubPeer?: Peer;
  private hub?: RoomCoordinator;
  private connection?: DataConnection;
  private locals = new Map<string, LocalPublication>();
  private incoming = new Map<string, MediaConnection>();
  private outgoing = new Map<string, { call: MediaConnection; publication: string }>();
  private requested = new Map<string, number>();
  private name = 'Visitante';
  private receiveCodecMode: CodecMode = 'auto';
  private generation = 0;
  private joined = false;
  private lastSeen = 0;
  private nextConnect = 0;
  private nextElection = 0;
  private started = 0;
  private creating = false;
  private signalingError = false;
  private turn?: TurnLease;
  private entry?: EntryDiagnostics;
  private timer?: ReturnType<typeof setInterval>;
  private factory: PeerFactory;
  constructor(factory: PeerFactory = makePeer) { this.factory = factory; }
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getSnapshot = () => this.snapshot;
  get sessionId() { return this.generation; }
  private update(change: Partial<RoomSnapshot>) {
    this.snapshot = { ...this.snapshot, ...change }; this.listeners.forEach(listener => listener());
  }
  private trace(event: string) {
    const line = `${new Date().toLocaleTimeString()} · ${event}`;
    console.info('[Room]', line);
    this.update({ diagnostics: [...this.snapshot.diagnostics.slice(-19), line] });
  }
  private catalog() { return [...this.locals.values()].map(({ id, title, kind }) => ({ id, title, kind })); }
  start(input: string, name: string, create: boolean, alternative?: TurnLease) {
    const room = normalizeRoom(input); if (!room) throw new Error('Use um código válido de sala.');
    void probeCodecs(qualityHint(undefined), 'decode');
    if (alternative && (!['error', 'idle', 'closed'].includes(this.snapshot.phase) || this.locals.size)) {
      throw new Error('A tentativa alternativa está disponível antes de entrar. Não interrompa uma transmissão ativa para ativá-la.');
    }
    const turn = alternative ? parseTurnLease(alternative) : undefined;
    this.leave(); this.name = displayName(name); this.started = Date.now(); this.creating = create; this.signalingError = false;
    this.turn = turn;
    this.entry = new EntryDiagnostics();
    this.update({ ...emptySnapshot(), room, phase: 'connecting', message: create ? 'Criando sala…' : 'Entrando…', transport: turn ? 'alternative' : 'direct', turnExpiresAt: turn?.expiresAt || 0, entry: this.entry.snapshot() });
    this.trace(turn ? 'Alternativa habilitada somente neste participante. Conexão direta continua permitida.' : HAS_TURN ? 'TURN configurado no build; disponibilidade da retransmissão ainda não verificada.' : 'Sem TURN configurado: a entrada e os vídeos dependem de conexão direta entre os participantes.');
    const generation = this.generation;
    let peer: Peer;
    try { peer = this.factory(undefined, this.participantOptions()); }
    catch { this.fail('Não foi possível inicializar a conexão neste ambiente. Confira suporte a WebRTC e tente novamente.', 'signaling'); return; }
    this.peer = peer;
    const current = () => this.peer === peer && this.generation === generation;
    peer.on('open', id => {
      if (!current()) return; this.signalingError = false; this.trace('Sinalização do participante conectada'); this.update({ selfId: id });
      if (create && !this.joined && !this.hubPeer) this.claimCoordinator(true); else this.connect();
    });
    peer.on('call', call => {
      const metadata: unknown = call.metadata;
      if (!current() || !metadata || typeof metadata !== 'object' || !('protocol' in metadata) || metadata.protocol !== PROTOCOL ||
        !('room' in metadata) || metadata.room !== room || !('publication' in metadata) || typeof metadata.publication !== 'string') { call.close(); return; }
      const id = metadata.publication;
      if (!this.snapshot.watching.includes(id) || !this.snapshot.participants.some(p => p.peerId === call.peer && p.publications.some(s => s.id === id))) { call.close(); return; }
      this.receive(id, call);
    });
    peer.on('connection', connection => connection.close());
    peer.on('disconnected', () => { if (current()) this.recover('Reconectando à sinalização…'); });
    peer.on('error', error => {
      if (!current()) return;
      this.trace(`Erro do participante: ${error.type}`);
      if (error.type === 'peer-unavailable') {
        if (!this.joined && !this.creating && !this.connection?.open) {
          this.fail(`A sala ${room} não foi encontrada nesta versão. Se você é o primeiro a entrar, clique em “Criar sala com este código”. Se alguém já está nela, confira se todos usam o app ou site atualizado.`, 'missing-room'); return;
        }
        if (!this.connection?.open && this.joined) this.recover('Trocando o coordenador da sala…'); return;
      }
      if (['network', 'socket-error', 'socket-closed', 'disconnected', 'server-error'].includes(error.type)) { this.signalingError = true; if (!this.joined) this.update({ message: 'Não foi possível alcançar a sinalização. Tentando reconectar…' }); else this.recover('Reconectando à sinalização…'); return; }
      if (error.type === 'webrtc') { this.update({ message: this.joined ? 'Uma conexão de mídia falhou. Use Tentar novamente; confira o diagnóstico antes de trocar a configuração de rede.' : 'A negociação da entrada falhou. Tentando novamente; confira o diagnóstico da conexão.' }); return; }
      this.fail(error.message);
    });
    peer.on('close', () => { if (current()) this.fail('A sinalização foi encerrada. Entre novamente.', 'closed'); });
    this.timer = setInterval(() => this.tick(), 1000);
  }
  private participantOptions(): PeerJSOption {
    const options = peerOptions();
    if (!this.turn) return options;
    return { ...options, config: { ...options.config, iceTransportPolicy: 'all',
      iceServers: structuredClone([...(options.config?.iceServers || []), ...this.turn.iceServers]) } };
  }
  renewTurn(value: TurnLease): boolean {
    if (!this.turn || !this.peer || !['connected', 'reconnecting'].includes(this.snapshot.phase)) return false;
    const lease = parseTurnLease(value);
    const base = peerOptions();
    const servers = structuredClone([...(base.config?.iceServers || []), ...lease.iceServers]);
    const media = this.connections();
    const connections = new Set([this.connection?.peerConnection, ...media.outgoing, ...media.incoming]);
    try {
      for (const connection of connections) {
        if (!connection || connection.connectionState === 'closed') continue;
        connection.setConfiguration({ ...connection.getConfiguration(), iceServers: structuredClone(servers), iceTransportPolicy: 'all' });
      }
      this.turn = lease;
      // PeerJS reads this instance's configuration when creating future connections.
      this.peer.options.config = this.participantOptions().config;
      this.update({ turnExpiresAt: lease.expiresAt, message: '' });
      this.trace('Credenciais alternativas renovadas neste participante, sem reiniciar vídeos ou sala.');
      return true;
    } catch {
      this.trace('Não foi possível confirmar a renovação em todas as conexões. A sala não foi reiniciada.');
      return false;
    }
  }
  private recover(message: string) {
    this.workspace.disconnect();
    if (!this.joined) return;
    if (this.snapshot.phase !== 'reconnecting') {
      const candidates = this.snapshot.participants.map(p => p.peerId).filter(id => id !== this.snapshot.coordinator).sort();
      const rank = Math.max(0, candidates.indexOf(this.snapshot.selfId));
      this.nextElection = Date.now() + 1500 + rank * 250;
    }
    this.update({ phase: 'reconnecting', message });
  }
  private claimCoordinator(initial: boolean) {
    if (this.hubPeer || !this.peer || this.peer.disconnected || this.peer.destroyed) return;
    this.trace('Registrando coordenação da sala');
    this.entry?.stage('coordinator');
    let hubPeer: Peer;
    try { hubPeer = this.factory(roomPeerId(this.snapshot.room), peerOptions()); }
    catch {
      this.nextElection = Date.now() + 4000;
      this.trace('Não foi possível iniciar o registro da coordenação; nova tentativa limitada ao prazo da entrada.');
      return;
    }
    this.hubPeer = hubPeer;
    const generation = this.generation;
    const current = () => this.hubPeer === hubPeer && this.generation === generation;
    hubPeer.on('open', () => {
      if (!current()) return;
      this.trace('Coordenação registrada');
      const seed = this.snapshot.participants.filter(p => p.peerId !== this.snapshot.coordinator || p.peerId === this.snapshot.selfId);
      this.hub = new RoomCoordinator(this.snapshot.selfId, seed, this.snapshot.workspace.snapshot);
      this.connect();
    });
    hubPeer.on('connection', connection => { if (current() && this.hub) this.hub.accept(connection); else connection.close(); });
    const lost = () => {
      if (!current()) return;
      this.hub?.close(false); this.hub = undefined; this.hubPeer = undefined; hubPeer.destroy();
      this.nextElection = Date.now() + 4000;
    };
    hubPeer.on('error', error => {
      if (!current()) return;
      this.trace(`Erro da coordenação: ${error.type}`);
      lost();
      if (initial && error.type === 'unavailable-id') { this.fail('Este código já está em uso. Entre na sala existente.', 'occupied-room'); return; }
      this.nextConnect = 0;
    });
    // Relinquish a disconnected lease. Only PeerServer may grant the room ID again.
    hubPeer.on('disconnected', lost); hubPeer.on('close', lost);
  }
  private send(message: ClientMessage) {
    if (this.connection?.open) { try { this.connection.send(message); return true; } catch (error) { console.warn('[Room]', error); } }
    return false;
  }
  private connect() {
    if (!this.peer || !this.snapshot.selfId || this.peer.disconnected || this.peer.destroyed) return;
    const previous = this.connection; this.connection = undefined; previous?.close();
    this.trace('Negociando conexão com a sala');
    this.entry?.negotiate();
    this.update({ entry: this.entry?.snapshot() || null });
    let connection: DataConnection;
    try { connection = this.peer.connect(roomPeerId(this.snapshot.room), { reliable: true, serialization: 'json', metadata: { protocol: PROTOCOL } }); }
    catch {
      this.nextConnect = Date.now() + 2000;
      this.trace('Não foi possível iniciar o canal da sala; aguardando nova tentativa.');
      this.recover('Reconectando ao canal da sala…'); return;
    }
    this.connection = connection; this.lastSeen = Date.now(); this.nextConnect = Date.now() + ROOM_NEGOTIATION_TIMEOUT_MS;
    if (!this.joined) this.update({ message: 'Negociando a conexão direta com a sala…' });
    const generation = this.generation;
    observeRoomConnection(connection, () => this.connection === connection && this.generation === generation, message => this.trace(message), value => {
      this.entry?.observe(value); this.update({ entry: this.entry?.snapshot() || null });
    });
    connection.on('open', () => {
      if (this.connection !== connection) return;
      this.trace('Canal da sala aberto; aguardando confirmação');
      this.entry?.stage('confirmation'); this.update({ entry: this.entry?.snapshot() || null });
      this.lastSeen = Date.now();
      if (!this.joined) this.update({ message: 'Conexão aberta. Aguardando a confirmação da sala…' });
      this.send({ type: 'join', protocol: PROTOCOL, name: this.name, publications: this.catalog(), extensions: [WORKSPACE_EXTENSION] });
    });
    connection.on('data', value => {
      if (this.connection !== connection) return;
      const message = parseServerMessage(value); if (!message) return;
      this.lastSeen = Date.now();
      switch (message.type) {
        case 'presence': {
          const resumed = this.snapshot.phase !== 'connected'; this.joined = true;
          if (resumed) this.trace('Entrada na sala confirmada');
          this.entry?.finish();
          this.update({ phase: 'connected', message: '', participants: message.participants, coordinator: message.coordinator, isHost: message.coordinator === this.snapshot.selfId, entry: this.entry?.snapshot() || null });
          this.workspace.capability(!!message.extensions?.includes(WORKSPACE_EXTENSION));
          if (resumed) { this.requested.clear(); for (const id of this.snapshot.watching) this.send({ type: 'watch', publication: id }); }
          this.synchronize(); break;
        }
        case 'subscribe': if (this.snapshot.participants.some(p => p.peerId === message.viewer)) this.publish(message.publication, message.viewer); break;
        case 'unsubscribe': this.stopOutgoing(this.key(message.publication, message.viewer)); break;
        case 'workspace-snapshot': case 'workspace-event': case 'workspace-result': this.workspace.receive(message); break;
        case 'migrate': {
          this.connection = undefined; connection.close(); this.recover('O coordenador saiu. Mantendo as transmissões e reorganizando a sala…'); this.nextConnect = 0; break;
        }
        case 'error': this.fail(message.message, 'rejected'); break;
      }
    });
    const lost = () => {
      if (this.connection !== connection) return;
      this.connection = undefined; connection.close(); this.nextConnect = Date.now() + 2000;
      if (!this.joined) this.update({ message: 'A tentativa não completou. Tentando conectar novamente…' });
      this.recover('Trocando o coordenador da sala…');
    };
    connection.on('close', lost); connection.on('error', lost);
  }
  setName(name: string) { this.name = displayName(name); this.send({ type: 'name', name: this.name }); }
  addLocal(publication: LocalPublication) {
    if (this.locals.size >= MAX_LOCAL_STREAMS) throw new Error(`Limite de ${MAX_LOCAL_STREAMS} transmissões por pessoa.`);
    void probeCodecs(publication.quality, 'encode');
    this.locals.set(publication.id, publication); this.send({ type: 'sharing', publications: this.catalog() });
  }
  removeLocal(id: string) {
    this.locals.delete(id);
    for (const [key, item] of this.outgoing) if (item.publication === id) this.stopOutgoing(key);
    this.send({ type: 'sharing', publications: this.catalog() });
  }
  setWatching(ids: string[]) {
    const available = new Set(this.snapshot.participants.filter(p => p.peerId !== this.snapshot.selfId).flatMap(p => p.publications.map(s => s.id)));
    const next = [...new Set(ids)].filter(id => available.has(id)).slice(0, MAX_WATCHING);
    for (const id of this.snapshot.watching) if (!next.includes(id)) {
      this.send({ type: 'unwatch', publication: id }); this.dropIncoming(id); this.requested.delete(id);
    }
    this.update({ watching: next }); this.synchronize();
  }
  retryWatching() {
    for (const id of this.snapshot.watching) { this.dropIncoming(id); this.requested.delete(id); }
    this.synchronize();
  }
  get receivingCodec() { return this.receiveCodecMode; }
  setReceivingCodec(value: CodecMode) {
    const mode = codecMode(value);
    if (this.receiveCodecMode === mode) return;
    this.receiveCodecMode = mode;
    if (this.snapshot.watching.length) this.retryWatching();
  }
  private synchronize() {
    if (this.snapshot.phase !== 'connected') return;
    const available = new Set(this.snapshot.participants.flatMap(p => p.publications.map(s => s.id)));
    const watching = this.snapshot.watching.filter(id => available.has(id));
    for (const id of this.snapshot.watching) if (!available.has(id)) { this.dropIncoming(id); this.requested.delete(id); }
    if (watching.length !== this.snapshot.watching.length) this.update({ watching });
    for (const id of watching) if (!this.incoming.has(id) && Date.now() - (this.requested.get(id) || 0) > 8000) {
      this.requested.set(id, Date.now()); this.send({ type: 'watch', publication: id });
    }
    for (const [key, item] of this.outgoing) if (!this.snapshot.participants.some(p => p.peerId === item.call.peer)) this.stopOutgoing(key);
  }
  private key(publication: string, viewer: string) { return JSON.stringify([publication, viewer]); }
  private publish(id: string, viewer: string) {
    const local = this.locals.get(id); const key = this.key(id, viewer);
    if (!local || !this.peer || this.outgoing.has(key)) return;
    const { resolution, fps, uploadMbps } = local.quality;
    const call = this.peer.call(viewer, local.stream, { metadata: { protocol: PROTOCOL, room: this.snapshot.room, publication: id,
      videoProfile: { resolution, fps, uploadMbps } }, sdpTransform: codecTransform(local.quality, 'encode') });
    this.outgoing.set(key, { call, publication: id });
    call.peerConnection.addEventListener('connectionstatechange', () => {
      if (call.peerConnection.connectionState === 'connected') this.retune();
      if (call.peerConnection.connectionState === 'failed') this.stopOutgoing(key);
    });
    const closed = () => { if (this.outgoing.get(key)?.call === call) this.stopOutgoing(key); };
    call.on('close', closed); call.on('error', closed); this.retune();
  }
  private retune() {
    // One overall upload ceiling across every active source and recipient.
    const uploadMbps = Math.min(...[...this.locals.values()].map(p => p.quality.uploadMbps));
    for (const item of this.outgoing.values()) {
      const quality = this.locals.get(item.publication)?.quality;
      if (quality) void tuneConnection(item.call.peerConnection, { ...quality, uploadMbps }, this.outgoing.size);
    }
  }
  private stopOutgoing(key: string) { const item = this.outgoing.get(key); this.outgoing.delete(key); item?.call.close(); this.retune(); }
  private receive(id: string, call: MediaConnection) {
    this.dropIncoming(id); this.incoming.set(id, call);
    const closed = () => { if (this.incoming.get(id) === call) this.dropIncoming(id); };
    const timer = setTimeout(() => { if (!this.snapshot.streams.has(id)) closed(); }, 15000);
    let disconnectTimer: ReturnType<typeof setTimeout> | undefined;
    const clear = () => { clearTimeout(timer); clearTimeout(disconnectTimer); };
    call.on('stream', stream => {
      if (this.incoming.get(id) !== call) return;
      clearTimeout(timer); const streams = new Map(this.snapshot.streams); streams.set(id, stream); this.update({ streams });
    });
    call.on('close', () => { clear(); closed(); }); call.on('error', () => { clear(); closed(); });
    const metadata: unknown = call.metadata;
    const value = metadata && typeof metadata === 'object' ? metadata as Record<string, unknown> : {};
    const profile = { ...qualityHint(value.videoProfile), codec: this.receiveCodecMode };
    // Cold probes are bounded to 800ms. Room admission and existing media never
    // wait. A cancelled/replaced incoming call must not be answered afterwards.
    void probeCodecs(profile, 'decode').then(() => {
      if (this.incoming.get(id) !== call) return;
      call.answer(undefined, { sdpTransform: codecTransform(profile, 'decode') });
      if (this.incoming.get(id) !== call || !call.peerConnection) return;
      call.peerConnection.addEventListener('connectionstatechange', () => {
        if (call.peerConnection.connectionState === 'failed') closed();
        if (call.peerConnection.connectionState === 'disconnected') { clearTimeout(disconnectTimer); disconnectTimer = setTimeout(closed, 12000); }
        if (call.peerConnection.connectionState === 'connected') clearTimeout(disconnectTimer);
      });
    });
  }
  private dropIncoming(id: string) {
    const call = this.incoming.get(id); this.incoming.delete(id); call?.close();
    if (this.snapshot.streams.has(id)) { const streams = new Map(this.snapshot.streams); streams.delete(id); this.update({ streams }); }
  }
  private tick() {
    const now = Date.now(); this.hub?.tick();
    if (this.turn && this.joined && now >= this.turn.expiresAt && !this.snapshot.message) {
      this.update({ message: 'O acesso à conexão alternativa venceu. Renove o acesso; conexões retransmitidas podem ser interrompidas pelo servidor.' });
    }
    if (!this.joined && now - this.started > 60000) {
      const message = !this.snapshot.selfId || this.signalingError
        ? 'Não foi possível conectar ao serviço de sinalização. Confira sua internet, firewall e a disponibilidade do serviço.'
        : this.creating && !this.hub
          ? 'A sinalização abriu, mas não foi possível registrar a sala. Tente criar novamente e confira a disponibilidade do serviço de sinalização.'
        : this.connection?.open
          ? 'A conexão abriu, mas a sala não confirmou a entrada. Confira se todos usam a mesma versão do app e do site.'
          : 'A conexão com a sala não completou. Se ela está aberta em outro computador, confira firewall/rede e a configuração TURN.';
      this.fail(message, !this.snapshot.selfId || this.signalingError ? 'signaling' : this.creating && !this.hub ? 'coordinator' : this.connection?.open ? 'confirmation' : 'transport'); return;
    }
    if (this.peer?.disconnected && !this.peer.destroyed && now >= this.nextConnect) {
      this.nextConnect = now + 5000; try { this.peer.reconnect(); } catch (error) { console.warn('[Room]', error); }
    }
    if (this.connection?.open) {
      this.send({ type: 'ping' });
      if (now - this.lastSeen > ROOM_JOIN_TIMEOUT_MS) {
        const previous = this.connection; this.connection = undefined; previous.close(); this.recover('A coordenação parou de responder. Reconectando…');
      }
    }
    if (!this.joined && this.creating && !this.hubPeer && now >= this.nextElection) this.claimCoordinator(true);
    if (!this.connection?.open && now >= this.nextConnect && (!this.creating || this.joined || this.hub)) this.connect();
    if (this.joined && this.snapshot.phase === 'reconnecting' && !this.connection?.open && now >= this.nextElection && !this.hubPeer) {
      this.nextElection = now + 5000; this.claimCoordinator(false);
    }
    this.synchronize();
  }
  connectionDetails() {
    return [
      ...[...this.outgoing.entries()].map(([id, item]) => ({ id, direction: 'outgoing' as const,
        title: this.locals.get(item.publication)?.title || 'Transmissão',
        quality: this.locals.get(item.publication)?.quality, connection: item.call.peerConnection })),
      ...[...this.incoming.entries()].map(([id, call]) => ({ id, direction: 'incoming' as const,
        title: this.snapshot.participants.flatMap(p => p.publications.map(publication => ({ ...publication, name: p.name })))
          .filter(publication => publication.id === id).map(publication => `${publication.name} · ${publication.title}`)[0] || 'Transmissão',
        quality: undefined, connection: call.peerConnection })),
    ];
  }
  connections() { return { outgoing: [...this.outgoing.values()].map(item => item.call.peerConnection), incoming: [...this.incoming.values()].map(call => call.peerConnection) }; }
  private fail(message: string, failure: EntryFailure = 'unknown') {
    this.entry?.finish(failure);
    const entry = this.entry?.snapshot() || null;
    const { diagnostics, transport, turnExpiresAt } = this.snapshot;
    this.leave(); this.update({ phase: 'error', message, diagnostics, transport, turnExpiresAt, entry });
  }
  leave() {
    this.workspace.reset();
    this.generation++; clearInterval(this.timer); this.timer = undefined;
    this.send({ type: 'leave' });
    this.hub?.close(true); this.hub = undefined;
    const hubPeer = this.hubPeer; this.hubPeer = undefined;
    if (hubPeer) setTimeout(() => hubPeer.destroy(), 150);
    const connection = this.connection; this.connection = undefined; connection?.close();
    const peer = this.peer; this.peer = undefined;
    for (const id of [...this.incoming.keys()]) this.dropIncoming(id);
    for (const key of [...this.outgoing.keys()]) this.stopOutgoing(key);
    peer?.destroy(); this.locals.clear(); this.requested.clear(); this.joined = false; this.turn = undefined; this.entry = undefined;
    this.nextConnect = 0; this.nextElection = 0; this.update(emptySnapshot());
  }
}
