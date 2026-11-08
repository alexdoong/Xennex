import { applyWorkspaceEvent, parseWorkspaceSnapshot, WORKSPACE_LIMITS, type WorkspaceSnapshot, type WorkspaceRequest, type WorkspaceReply, type WorkspaceChange, type WorkspaceResult } from './workspaceProtocol';

/** Coordinator-owned bounded session data. Actor identity comes from admitted connection. */
export class RoomWorkspaceState {
  private state: WorkspaceSnapshot;
  private results = new Map<string, Map<string, WorkspaceResult>>();
  private rates = new Map<string, { start: number; count: number; sync: number }>();
  private global = { start: 0, count: 0 };
  private now: () => number;
  constructor(seed?: WorkspaceSnapshot | null, now = () => Date.now()) {
    this.now = now;
    const previous = parseWorkspaceSnapshot(seed);
    this.state = { epoch: crypto.randomUUID(), revision: 0, messages: previous?.messages || [],
      note: previous?.note || { text: '', revision: 0 }, tasks: previous?.tasks || [] };
  }
  snapshot(): Extract<WorkspaceReply, { type: 'workspace-snapshot' }> { return { type: 'workspace-snapshot', snapshot: structuredClone(this.state) }; }
  remove(peerId: string) { this.results.delete(peerId); this.rates.delete(peerId); }
  clear() { this.results.clear(); this.rates.clear(); this.state = { epoch: crypto.randomUUID(), revision: 0, messages: [], note: { text: '', revision: 0 }, tasks: [] }; }
  handle(actor: { peerId: string; name: string }, request: WorkspaceRequest): { direct: WorkspaceReply[]; event?: WorkspaceReply } {
    const now = this.now();
    let rate = this.rates.get(actor.peerId);
    if (!rate) { rate = { start: now, count: 0, sync: -Infinity }; this.rates.set(actor.peerId, rate); }
    if (now - rate.start >= 10000) { rate.start = now; rate.count = 0; }
    if (request.type === 'workspace-sync') {
      if (now - rate.sync < 5000) return { direct: [] };
      rate.sync = now; return { direct: [this.snapshot()] };
    }
    const result = (value: WorkspaceResult) => ({ type: 'workspace-result' as const, id: request.id, result: value });
    if (++rate.count > 12) return { direct: [result({ ok: false, reason: 'limited' })] };
    const remembered = this.results.get(actor.peerId)?.get(request.id);
    if (remembered) return { direct: [result(remembered)] };
    if (request.epoch !== this.state.epoch) return { direct: [result({ ok: false, reason: 'conflict' })] };
    if (now - this.global.start >= 10000) this.global = { start: now, count: 0 };
    if (++this.global.count > 40) return { direct: [result({ ok: false, reason: 'limited' })] };
    const action = request.action;
    let change: WorkspaceChange;
    if (action.kind === 'note') {
      if (action.baseRevision !== this.state.note.revision) return { direct: [result({ ok: false, reason: 'conflict' })] };
      change = { kind: 'note', text: action.text, revision: this.state.note.revision + 1 };
    } else if (action.kind === 'chat') change = { kind: 'chat', entry: { id: crypto.randomUUID(), author: actor.peerId, name: actor.name, text: action.text } };
    else change = action;
    if (action.kind === 'task-add' && this.state.tasks.length >= WORKSPACE_LIMITS.tasks) return { direct: [result({ ok: false, reason: 'limited' })] };
    const event: Extract<WorkspaceReply, { type: 'workspace-event' }> = { type: 'workspace-event', epoch: this.state.epoch, revision: this.state.revision + 1, change };
    const next = applyWorkspaceEvent(this.state, event);
    if (!next) return { direct: [result({ ok: false, reason: 'missing' })] };
    this.state = next;
    let rememberedResults = this.results.get(actor.peerId);
    if (!rememberedResults) { rememberedResults = new Map(); this.results.set(actor.peerId, rememberedResults); }
    rememberedResults.set(request.id, { ok: true });
    if (rememberedResults.size > 64) rememberedResults.delete(rememberedResults.keys().next().value!);
    return { direct: [result({ ok: true })], event };
  }
}
