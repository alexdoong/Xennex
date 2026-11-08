import type { DataConnection } from 'peerjs';
import { RoomWorkspaceState } from './RoomWorkspaceState';
import { WORKSPACE_EXTENSION, type WorkspaceSnapshot } from './workspaceProtocol';
import { MAX_PARTICIPANTS, MAX_WATCHING, parseClientMessage, type Participant, type Publication, type ServerMessage } from './protocol';

export const ROOM_NEGOTIATION_TIMEOUT_MS = 25000;
export const ROOM_JOIN_TIMEOUT_MS = 10000;

/** Replaceable control plane. Media never passes through the coordinator. */
export class RoomCoordinator {
  private members = new Map<string, DataConnection>();
  private roster = new Map<string, Participant>();
  private seen = new Map<string, number>();
  private watches = new Map<string, Set<string>>();
  private pending = new Set<DataConnection>();
  private closed = false;
  private owner: string;
  private workspace: RoomWorkspaceState;
  private workspaceMembers = new Set<string>();
  constructor(owner: string, seed: Participant[], workspaceSeed?: WorkspaceSnapshot | null) {
    this.owner = owner;
    this.workspace = new RoomWorkspaceState(workspaceSeed);
    for (const participant of seed) { this.roster.set(participant.peerId, participant); this.seen.set(participant.peerId, Date.now()); }
  }
  private send(connection: DataConnection | undefined, message: ServerMessage) {
    if (connection?.open) { try { connection.send(message); } catch (error) { console.warn('[Room hub]', error); } }
  }
  private broadcast() {
    if (!this.roster.has(this.owner)) return;
    const message: ServerMessage = { type: 'presence', participants: [...this.roster.values()], coordinator: this.owner, extensions: [WORKSPACE_EXTENSION] };
    this.members.forEach(connection => this.send(connection, message));
  }
  private validPublications(id: string, publications: Publication[]) {
    return ![...this.roster.values()].some(p => p.peerId !== id && p.publications.some(old => publications.some(next => next.id === old.id)));
  }
  accept(connection: DataConnection) {
    if (this.closed) { connection.close(); return; }
    this.pending.add(connection);
    let finished = false;
    const expire = () => { if (!finished) connection.close(); };
    let timer = setTimeout(expire, ROOM_NEGOTIATION_TIMEOUT_MS);
    const opened = () => {
      if (finished) return;
      clearTimeout(timer);
      timer = setTimeout(expire, ROOM_JOIN_TIMEOUT_MS);
    };
    connection.on('open', opened);
    if (connection.open) opened();
    connection.on('data', value => {
      if (this.closed) return;
      const message = parseClientMessage(value); if (!message) return;
      const id = connection.peer;
      if (message.type === 'join') {
        if (finished && this.members.get(id) === connection) return;
        if (!this.roster.has(id) && this.roster.size >= MAX_PARTICIPANTS) {
          this.send(connection, { type: 'error', message: `Sala cheia (${MAX_PARTICIPANTS} participantes).` });
          setTimeout(() => connection.close(), 200); return;
        }
        if (!this.validPublications(id, message.publications)) return;
        finished = true; clearTimeout(timer); connection.off('open', opened); this.pending.delete(connection);
        const previous = this.members.get(id); this.members.set(id, connection); if (previous !== connection) previous?.close();
        this.roster.set(id, { peerId: id, name: message.name, publications: message.publications });
        const supportsWorkspace = message.extensions?.includes(WORKSPACE_EXTENSION);
        if (supportsWorkspace) this.workspaceMembers.add(id); else this.workspaceMembers.delete(id);
        this.seen.set(id, Date.now()); this.broadcast();
        if (supportsWorkspace) this.send(connection, this.workspace.snapshot());
        return;
      }
      if (this.members.get(id) !== connection) return;
      this.seen.set(id, Date.now());
      const participant = this.roster.get(id)!;
      switch (message.type) {
        case 'workspace-operation': case 'workspace-sync': {
          if (!this.workspaceMembers.has(id)) return;
          const result = this.workspace.handle(participant, message);
          if (result.event) for (const member of this.workspaceMembers) this.send(this.members.get(member), result.event);
          result.direct.forEach(reply => this.send(connection, reply));
          break;
        }
        case 'name': this.roster.set(id, { ...participant, name: message.name }); this.broadcast(); break;
        case 'sharing':
          if (!this.validPublications(id, message.publications)) return;
          this.roster.set(id, { ...participant, publications: message.publications });
          for (const old of participant.publications) if (!message.publications.some(p => p.id === old.id)) this.watches.delete(old.id);
          this.broadcast(); break;
        case 'watch': case 'unwatch': {
          const publisher = [...this.roster.values()].find(p => p.publications.some(s => s.id === message.publication));
          if (!publisher || publisher.peerId === id) return;
          const viewers = this.watches.get(message.publication) || new Set<string>();
          if (message.type === 'watch') {
            if (!viewers.has(id) && [...this.watches.values()].filter(v => v.has(id)).length >= MAX_WATCHING) return;
            viewers.add(id);
          } else viewers.delete(id);
          this.watches.set(message.publication, viewers);
          this.send(this.members.get(publisher.peerId), { type: message.type === 'watch' ? 'subscribe' : 'unsubscribe', publication: message.publication, viewer: id });
          break;
        }
        case 'ping': this.send(connection, { type: 'pong' }); break;
        case 'leave': this.remove(id); break;
      }
    });
    const lost = () => {
      finished = true; clearTimeout(timer); connection.off('open', opened); this.pending.delete(connection);
      if (this.members.get(connection.peer) === connection) this.remove(connection.peer);
    };
    connection.on('close', lost); connection.on('error', lost);
  }
  private remove(id: string) {
    this.workspaceMembers.delete(id); this.workspace.remove(id);
    const participant = this.roster.get(id);
    const connection = this.members.get(id); this.members.delete(id); this.roster.delete(id); this.seen.delete(id); connection?.close();
    for (const publication of participant?.publications || []) this.watches.delete(publication.id);
    for (const [publication, viewers] of this.watches) {
      if (!viewers.delete(id)) continue;
      const publisher = [...this.roster.values()].find(p => p.publications.some(s => s.id === publication));
      if (publisher) this.send(this.members.get(publisher.peerId), { type: 'unsubscribe', publication, viewer: id });
    }
    this.broadcast();
  }
  tick() { for (const [id, time] of this.seen) if (Date.now() - time > 20000) this.remove(id); }
  close(notify: boolean) {
    this.closed = true;
    if (notify) this.members.forEach(connection => this.send(connection, { type: 'migrate' }));
    this.pending.forEach(connection => connection.close()); this.pending.clear();
    this.members.clear(); this.roster.clear(); this.seen.clear(); this.watches.clear();
    this.workspaceMembers.clear(); this.workspace.clear();
  }
}
