// Optional extension to room-v3. Older coordinators/clients continue media-only.
export const WORKSPACE_EXTENSION = 'workspace-v1' as const;
export const WORKSPACE_LIMITS = { messages: 20, message: 1000, note: 8000, tasks: 32, title: 160 } as const;
export interface ChatEntry { id: string; author: string; name: string; text: string }
export interface SharedTask { id: string; title: string; done: boolean }
export interface WorkspaceSnapshot {
  epoch: string; revision: number; messages: ChatEntry[];
  note: { text: string; revision: number }; tasks: SharedTask[];
}
export type WorkspaceAction =
  | { kind: 'chat'; text: string }
  | { kind: 'note'; text: string; baseRevision: number }
  | { kind: 'task-add'; id: string; title: string }
  | { kind: 'task-set'; id: string; done: boolean }
  | { kind: 'task-remove'; id: string };
export type WorkspaceChange = Exclude<WorkspaceAction, { kind: 'chat' | 'note' }>
  | { kind: 'chat'; entry: ChatEntry }
  | { kind: 'note'; text: string; revision: number };
export type WorkspaceFailure = 'conflict' | 'limited' | 'missing' | 'unavailable' | 'timeout';
export type WorkspaceResult = { ok: true } | { ok: false; reason: WorkspaceFailure };
export type WorkspaceRequest = { type: 'workspace-operation'; id: string; epoch: string; action: WorkspaceAction } | { type: 'workspace-sync' };
export type WorkspaceReply =
  | { type: 'workspace-snapshot'; snapshot: WorkspaceSnapshot }
  | { type: 'workspace-event'; epoch: string; revision: number; change: WorkspaceChange }
  | { type: 'workspace-result'; id: string; result: WorkspaceResult };
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
export const workspaceId = (value: unknown): value is string => typeof value === 'string' && /^[\w-]{1,100}$/.test(value);
const revision = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
const text = (value: unknown, max: number, empty = false): value is string => {
  if (typeof value !== 'string' || value.length > max || (!empty && !value.trim())) return false;
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code < 32 && code !== 9 && code !== 10 && code !== 13) return false;
  }
  return true;
};

export function parseWorkspaceAction(value: unknown): WorkspaceAction | null {
  if (!record(value)) return null;
  switch (value.kind) {
    case 'chat': return text(value.text, WORKSPACE_LIMITS.message) ? { kind: 'chat', text: value.text } : null;
    case 'note': return text(value.text, WORKSPACE_LIMITS.note, true) && revision(value.baseRevision) ? { kind: 'note', text: value.text, baseRevision: value.baseRevision } : null;
    case 'task-add': return workspaceId(value.id) && text(value.title, WORKSPACE_LIMITS.title) ? { kind: value.kind, id: value.id, title: value.title } : null;
    case 'task-set': return workspaceId(value.id) && typeof value.done === 'boolean' ? { kind: value.kind, id: value.id, done: value.done } : null;
    case 'task-remove': return workspaceId(value.id) ? { kind: value.kind, id: value.id } : null;
    default: return null;
  }
}
export function parseWorkspaceRequest(value: unknown): WorkspaceRequest | null {
  if (!record(value)) return null;
  if (value.type === 'workspace-sync') return { type: 'workspace-sync' };
  if (value.type !== 'workspace-operation' || !workspaceId(value.id) || !workspaceId(value.epoch)) return null;
  const action = parseWorkspaceAction(value.action);
  return action ? { type: 'workspace-operation', id: value.id, epoch: value.epoch, action } : null;
}
function parseEntry(value: unknown): ChatEntry | null {
  return record(value) && workspaceId(value.id) && workspaceId(value.author) && text(value.name, 40) && text(value.text, WORKSPACE_LIMITS.message)
    ? { id: value.id, author: value.author, name: value.name, text: value.text } : null;
}
function parseChange(value: unknown): WorkspaceChange | null {
  if (!record(value)) return null;
  if (value.kind === 'chat') { const entry = parseEntry(value.entry); return entry ? { kind: 'chat', entry } : null; }
  if (value.kind === 'note') return text(value.text, WORKSPACE_LIMITS.note, true) && revision(value.revision) ? { kind: 'note', text: value.text, revision: value.revision } : null;
  const action = parseWorkspaceAction(value);
  return action && action.kind !== 'chat' && action.kind !== 'note' ? action : null;
}
export function parseWorkspaceSnapshot(value: unknown): WorkspaceSnapshot | null {
  if (!record(value) || !workspaceId(value.epoch) || !revision(value.revision) || !Array.isArray(value.messages) || value.messages.length > WORKSPACE_LIMITS.messages ||
      !Array.isArray(value.tasks) || value.tasks.length > WORKSPACE_LIMITS.tasks || !record(value.note) || !text(value.note.text, WORKSPACE_LIMITS.note, true) || !revision(value.note.revision)) return null;
  const messages: ChatEntry[] = [], tasks: SharedTask[] = [];
  for (const item of value.messages) {
    const entry = parseEntry(item);
    if (!entry || messages.some(old => old.id === entry.id)) return null;
    messages.push(entry);
  }
  for (const item of value.tasks) {
    if (!record(item) || !workspaceId(item.id) || !text(item.title, WORKSPACE_LIMITS.title) || typeof item.done !== 'boolean' || tasks.some(old => old.id === item.id)) return null;
    tasks.push({ id: item.id, title: item.title, done: item.done });
  }
  return { epoch: value.epoch, revision: value.revision, messages, tasks, note: { text: value.note.text, revision: value.note.revision } };
}
export function parseWorkspaceReply(value: unknown): WorkspaceReply | null {
  if (!record(value)) return null;
  if (value.type === 'workspace-snapshot') {
    const snapshot = parseWorkspaceSnapshot(value.snapshot);
    return snapshot ? { type: value.type, snapshot } : null;
  }
  if (value.type === 'workspace-event' && workspaceId(value.epoch) && revision(value.revision)) {
    const change = parseChange(value.change);
    return change ? { type: value.type, epoch: value.epoch, revision: value.revision, change } : null;
  }
  if (value.type !== 'workspace-result' || !workspaceId(value.id) || !record(value.result)) return null;
  if (value.result.ok === true) return { type: value.type, id: value.id, result: { ok: true } };
  const reasons: WorkspaceFailure[] = ['conflict', 'limited', 'missing', 'unavailable', 'timeout'];
  return value.result.ok === false && reasons.includes(value.result.reason as WorkspaceFailure)
    ? { type: value.type, id: value.id, result: { ok: false, reason: value.result.reason as WorkspaceFailure } } : null;
}

// Pure reducer shared by coordinator and replica. Gaps require a bounded snapshot.
export function applyWorkspaceEvent(state: WorkspaceSnapshot, event: Extract<WorkspaceReply, { type: 'workspace-event' }>): WorkspaceSnapshot | null {
  if (event.epoch !== state.epoch || event.revision !== state.revision + 1) return null;
  const change = event.change, next = { ...state, revision: event.revision };
  switch (change.kind) {
    case 'chat':
      if (state.messages.some(entry => entry.id === change.entry.id)) return null;
      return { ...next, messages: [...state.messages, change.entry].slice(-WORKSPACE_LIMITS.messages) };
    case 'note': return change.revision === state.note.revision + 1 ? { ...next, note: { text: change.text, revision: change.revision } } : null;
    case 'task-add': return state.tasks.length < WORKSPACE_LIMITS.tasks && !state.tasks.some(task => task.id === change.id)
      ? { ...next, tasks: [...state.tasks, { id: change.id, title: change.title, done: false }] } : null;
    case 'task-set': return state.tasks.some(task => task.id === change.id) ? { ...next, tasks: state.tasks.map(task => task.id === change.id ? { ...task, done: change.done } : task) } : null;
    case 'task-remove': return state.tasks.some(task => task.id === change.id) ? { ...next, tasks: state.tasks.filter(task => task.id !== change.id) } : null;
  }
}
