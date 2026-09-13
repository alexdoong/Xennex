import type { DataConnection } from 'peerjs';
import { MAX_PARTICIPANTS, MAX_WATCHING, parseClientMessage, type Participant, type Publication, type ServerMessage } from './protocol';

/** Replaceable control plane. Media never passes through the coordinator. */
export class RoomCoordinator {
  private members = new Map<string, DataConnection>();
  private roster = new Map<string, Participant>();
  private seen = new Map<string, number>();
  private watches = new Map<string, Set<string>>();
  private pending = new Set<DataConnection>();
  private closed = false;
  private owner: string;
  constructor(owner: string, seed: Participant[]) {
    this.owner = owner;
    for (const participant of seed) { this.roster.set(participant.peerId, participant); this.seen.set(participant.peerId, Date.now()); }
  }
  private send(connection: DataConnection | undefined, message: ServerMessage) {
    if (connection?.open) { try { connection.send(message); } catch (error) { console.warn('[Room hub]', error); } }
  }
  private broadcast() {
    if (!this.roster.has(this.owner)) return;
    const message: ServerMessage = { type: 'presence', participants: [...this.roster.values()], coordinator: this.owner };
    this.members.forEach(connection => this.send(connection, message));
  }
  private validPublications(id: string, publications: Publication[]) {
    return ![...this.roster.values()].some(p => p.peerId !== id && p.publications.some(old => publications.some(next => next.id === old.id)));
  }
  accept(connection: DataConnection) {
    if (this.closed) { connection.close(); return; }
    this.pending.add(connection);
    const timer = setTimeout(() => { if (this.members.get(connection.peer) !== connection) connection.close(); }, 10000);
    connection.on('data', value => {
      if (this.closed) return;
      const message = parseClientMessage(value); if (!message) return;
      const id = connection.peer;
      if (message.type === 'join') {
        if (!this.roster.has(id) && this.roster.size >= MAX_PARTICIPANTS) {
          this.send(connection, { type: 'error', message: `Sala cheia (${MAX_PARTICIPANTS} participantes).` });
          setTimeout(() => connection.close(), 200); return;
        }
        if (!this.validPublications(id, message.publications)) return;
        clearTimeout(timer); this.pending.delete(connection);
        const previous = this.members.get(id); this.members.set(id, connection); if (previous !== connection) previous?.close();
        this.roster.set(id, { peerId: id, name: message.name, publications: message.publications });
        this.seen.set(id, Date.now()); this.broadcast(); return;
      }
      if (this.members.get(id) !== connection) return;
      this.seen.set(id, Date.now());
      const participant = this.roster.get(id)!;
      switch (message.type) {
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
      clearTimeout(timer); this.pending.delete(connection);
      if (this.members.get(connection.peer) === connection) this.remove(connection.peer);
    };
    connection.on('close', lost); connection.on('error', lost);
  }
  private remove(id: string) {
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
  }
}
