import { WORKSPACE_EXTENSION, parseWorkspaceRequest, parseWorkspaceReply, type WorkspaceRequest, type WorkspaceReply } from './workspaceProtocol';
export const PROTOCOL = 'xennex-room-v3' as const;
export const MAX_PARTICIPANTS = 32;
export const MAX_LOCAL_STREAMS = 6;
export const MAX_WATCHING = 32;
export type RoomPhase = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'error' | 'closed';
export interface Publication { id: string; title: string; kind: 'screen' | 'camera' }
export interface Participant { peerId: string; name: string; publications: Publication[] }
export type ClientMessage = WorkspaceRequest
  | { type: 'join'; name: string; publications: Publication[]; protocol: typeof PROTOCOL; extensions?: string[] }
  | { type: 'name'; name: string }
  | { type: 'sharing'; publications: Publication[] }
  | { type: 'watch' | 'unwatch'; publication: string }
  | { type: 'ping' | 'leave' };
export type ServerMessage = WorkspaceReply
  | { type: 'presence'; participants: Participant[]; coordinator: string; extensions?: string[] }
  | { type: 'subscribe' | 'unsubscribe'; viewer: string; publication: string }
  | { type: 'pong' | 'migrate' }
  | { type: 'error'; message: string };
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object';
const short = (value: unknown, max = 100): value is string => typeof value === 'string' && value.length > 0 && value.length <= max;
const extensions = (value: unknown): { extensions?: string[] } => Array.isArray(value) && value.length <= 8 && value.includes(WORKSPACE_EXTENSION) ? { extensions: [WORKSPACE_EXTENSION] } : {};
export function parsePublications(value: unknown): Publication[] | null {
  if (!Array.isArray(value) || value.length > MAX_LOCAL_STREAMS) return null;
  const result: Publication[] = [];
  for (const item of value) {
    if (!record(item) || !short(item.id, 80) || !short(item.title, 80) ||
      (item.kind !== 'screen' && item.kind !== 'camera') || result.some(p => p.id === item.id)) return null;
    result.push({ id: item.id, title: item.title, kind: item.kind });
  }
  return result;
}
export function parseClientMessage(value: unknown): ClientMessage | null {
  if (!record(value)) return null;
  switch (value.type) {
    case 'join': {
      const publications = parsePublications(value.publications);
      return value.protocol === PROTOCOL && short(value.name, 40) && publications ? { type: 'join', protocol: PROTOCOL, name: value.name, publications, ...extensions(value.extensions) } : null;
    }
    case 'name': return short(value.name, 40) ? { type: 'name', name: value.name } : null;
    case 'sharing': { const publications = parsePublications(value.publications); return publications ? { type: 'sharing', publications } : null; }
    case 'watch': case 'unwatch': return short(value.publication, 80) ? { type: value.type, publication: value.publication } : null;
    case 'ping': case 'leave': return { type: value.type };
    default: return parseWorkspaceRequest(value);
  }
}
export function parseServerMessage(value: unknown): ServerMessage | null {
  if (!record(value)) return null;
  if (typeof value.type === 'string' && value.type.startsWith('workspace-')) return parseWorkspaceReply(value);
  if (value.type === 'pong' || value.type === 'migrate') return { type: value.type };
  if (value.type === 'error' && short(value.message, 250)) return { type: 'error', message: value.message };
  if ((value.type === 'subscribe' || value.type === 'unsubscribe') && short(value.viewer) && short(value.publication, 80))
    return { type: value.type, viewer: value.viewer, publication: value.publication };
  if (value.type !== 'presence' || !short(value.coordinator) || !Array.isArray(value.participants) || value.participants.length > MAX_PARTICIPANTS) return null;
  const participants: Participant[] = [];
  const ids = new Set<string>();
  for (const p of value.participants) {
    if (!record(p) || !short(p.peerId) || !short(p.name, 40)) return null;
    const publications = parsePublications(p.publications);
    if (!publications || participants.some(existing => existing.peerId === p.peerId)) return null;
    for (const publication of publications) { if (ids.has(publication.id)) return null; ids.add(publication.id); }
    participants.push({ peerId: p.peerId, name: p.name, publications });
  }
  if (!participants.some(p => p.peerId === value.coordinator)) return null;
  return { type: 'presence', participants, coordinator: value.coordinator, ...extensions(value.extensions) };
}
export function normalizeRoom(value: string): string {
  let input = value.trim();
  if (/^https?:\/\//i.test(input)) {
    try { input = new URL(input).searchParams.get('room') || ''; } catch { return ''; }
  }
  const code = input.toUpperCase();
  return /^[A-Z0-9][A-Z0-9_-]{2,39}$/.test(code) ? code : '';
}
export function newRoomCode(): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return 'XNX-' + Array.from(bytes, byte => alphabet[byte % alphabet.length]).join('');
}
export const roomPeerId = (room: string) => `xennex-v3-${room.toLowerCase()}`;
export const displayName = (name: string) => name.trim().slice(0, 40) || 'Visitante';
export function roomLink(base: string, room: string): string {
  const url = new URL(base.includes('://') ? base : `https://${base}`);
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Use um endereço HTTP ou HTTPS.');
  url.search = ''; url.hash = ''; url.searchParams.set('room', room);
  return url.toString();
}
