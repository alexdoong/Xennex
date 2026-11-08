import type { Participant } from './protocol';

export interface NewScreenShare { key: string; peerId: string; publicationId: string; name: string; title: string }
const keyFor = (peerId: string, publicationId: string) => JSON.stringify([peerId, publicationId]);

// Presence is a repeated snapshot, not an event feed. Keep bounded session history
// so heartbeat/rename/coordinator recovery cannot announce the same source twice.
export class StreamAnnouncements {
  private session = '';
  private initialized = false;
  private seen = new Set<string>();
  private unread = new Map<string, NewScreenShare>();
  reset() { this.session = ''; this.initialized = false; this.seen.clear(); this.unread.clear(); }
  update(session: string, participants: Participant[], selfId: string, watching: readonly string[]): NewScreenShare[] {
    if (session !== this.session) { this.reset(); this.session = session; }
    const screens = participants.filter(p => p.peerId !== selfId).flatMap(p => p.publications.filter(v => v.kind === 'screen').map(v => ({
      key: keyFor(p.peerId, v.id), peerId: p.peerId, publicationId: v.id, name: p.name, title: v.title,
    })));
    const active = new Set(screens.map(s => s.key)), watched = new Set(watching);
    for (const screen of screens) {
      if (this.initialized && !this.seen.has(screen.key) && !watched.has(screen.publicationId)) this.unread.set(screen.key, screen);
      this.seen.add(screen.key);
      if (this.unread.has(screen.key)) this.unread.set(screen.key, screen); // Rename without a new event.
    }
    this.initialized = true;
    for (const [key, screen] of this.unread) if (!active.has(key) || watched.has(screen.publicationId)) this.unread.delete(key);
    if (this.seen.size > 2048) for (const key of this.seen) {
      if (!active.has(key)) this.seen.delete(key);
      if (this.seen.size <= 2048) break;
    }
    return [...this.unread.values()];
  }
}
