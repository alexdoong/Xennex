import { applyWorkspaceEvent, parseWorkspaceAction, type WorkspaceRequest, type WorkspaceReply, type WorkspaceSnapshot, type WorkspaceAction, type WorkspaceResult } from './workspaceProtocol';
export interface WorkspaceView { available: boolean; snapshot: WorkspaceSnapshot | null; synchronizing: boolean }
export const emptyWorkspaceView = (): WorkspaceView => ({ available: false, snapshot: null, synchronizing: false });

/** Optional room extension. No native access, persistence, media or React state. */
export class RoomWorkspaceClient {
  private state = emptyWorkspaceView();
  private pending = new Map<string, { resolve(result: WorkspaceResult): void; timer: ReturnType<typeof setTimeout> }>();
  private lastSync = -Infinity;
  private send: (request: WorkspaceRequest) => boolean;
  private changed: (state: WorkspaceView) => void;
  constructor(send: (request: WorkspaceRequest) => boolean, changed: (state: WorkspaceView) => void) { this.send = send; this.changed = changed; }
  private update(change: Partial<WorkspaceView>) { this.state = { ...this.state, ...change }; this.changed(this.state); }
  capability(available: boolean) {
    if (available === this.state.available) return;
    this.update({ available, synchronizing: available });
    if (!available) this.cancel();
  }
  disconnect() { this.cancel(); this.update({ available: false, synchronizing: false }); this.lastSync = -Infinity; }
  reset() { this.cancel(); this.lastSync = -Infinity; this.state = emptyWorkspaceView(); this.changed(this.state); }
  private cancel() {
    for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.resolve({ ok: false, reason: 'unavailable' }); }
    this.pending.clear();
  }
  sync() {
    if (!this.state.available || Date.now() - this.lastSync < 5000) return;
    this.lastSync = Date.now(); this.update({ synchronizing: true }); this.send({ type: 'workspace-sync' });
  }
  receive(message: WorkspaceReply) {
    if (!this.state.available) return;
    if (message.type === 'workspace-result') {
      const pending = this.pending.get(message.id); if (!pending) return;
      this.pending.delete(message.id); clearTimeout(pending.timer); pending.resolve(message.result);
      if (!message.result.ok && message.result.reason === 'conflict') this.sync();
      return;
    }
    if (message.type === 'workspace-snapshot') {
      if (this.state.snapshot?.epoch === message.snapshot.epoch && message.snapshot.revision < this.state.snapshot.revision) return;
      this.update({ snapshot: message.snapshot, synchronizing: false }); return;
    }
    const snapshot = this.state.snapshot;
    if (snapshot?.epoch === message.epoch && message.revision <= snapshot.revision) return;
    const next = snapshot && applyWorkspaceEvent(snapshot, message);
    if (!next) { this.sync(); return; }
    this.update({ snapshot: next });
  }
  dispatch(input: WorkspaceAction): Promise<WorkspaceResult> {
    const action = parseWorkspaceAction(input), snapshot = this.state.snapshot;
    if (!action || !this.state.available || this.state.synchronizing || !snapshot) return Promise.resolve({ ok: false, reason: 'unavailable' });
    if (this.pending.size >= 4) return Promise.resolve({ ok: false, reason: 'limited' });
    const id = crypto.randomUUID();
    return new Promise(resolve => {
      const timer = setTimeout(() => { this.pending.delete(id); resolve({ ok: false, reason: 'timeout' }); }, 8000);
      this.pending.set(id, { resolve, timer });
      if (!this.send({ type: 'workspace-operation', id, epoch: snapshot.epoch, action })) {
        clearTimeout(timer); this.pending.delete(id); resolve({ ok: false, reason: 'unavailable' });
      }
    });
  }
}
