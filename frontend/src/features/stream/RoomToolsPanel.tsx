import { useState } from 'react';
import type { RoomWorkspaceClient, WorkspaceView } from './RoomWorkspaceClient';
import { WORKSPACE_LIMITS, type WorkspaceAction, type WorkspaceFailure } from './workspaceProtocol';

const failures: Record<WorkspaceFailure, string> = {
  conflict: 'A versão da sala mudou. Confira o conteúdo atual antes de salvar novamente.',
  limited: 'Limite de conteúdo ou de operações atingido. Aguarde um pouco ou remova itens antigos.',
  missing: 'Esse item foi alterado ou removido. Confira a versão atual da sala.',
  unavailable: 'As ferramentas ainda não estão disponíveis nesta conexão.',
  timeout: 'A confirmação não chegou. Confira a sala antes de repetir: a operação pode ter sido recebida.',
};

export default function RoomToolsPanel({ view, client }: { view: WorkspaceView; client: RoomWorkspaceClient }) {
  const [chat, setChat] = useState('');
  const [task, setTask] = useState('');
  const [draft, setDraft] = useState<{ text: string; baseRevision: number; epoch: string } | null>(null);
  const [pendingTasks, setPendingTasks] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const snapshot = view.snapshot;
  const disabled = busy || !view.available || view.synchronizing || !snapshot;
  const perform = async (action: WorkspaceAction, accepted?: () => void) => {
    if (disabled) return;
    setBusy(true); setNotice('');
    try {
      const result = await client.dispatch(action);
      if (result.ok) accepted?.(); else setNotice(failures[result.reason]);
    } finally { setBusy(false); }
  };
  return <section className="room-tools" aria-label="Conversa e ferramentas da sala">
    <header><strong>Conversa, notas e tarefas</strong><button type="button" disabled={!view.available || busy} onClick={() => client.sync()}>Atualizar conteúdo</button></header>
    <p className="room-helper">Conteúdo compartilhado com quem está na sala e mantido apenas nesta sessão. Todos podem editar notas e tarefas. As últimas {WORKSPACE_LIMITS.messages} mensagens ficam disponíveis para quem entrar.</p>
    {!view.available && <p role="status">Aguardando uma conexão compatível com as ferramentas. Transmissões continuam independentes.</p>}
    {view.synchronizing && <p role="status">Sincronizando conteúdo…</p>}
    {notice && <p role="status">{notice}</p>}
    {snapshot && <div className="room-tools-columns">
      <div><h3>Conversa</h3><ol className="room-chat-messages" aria-label="Mensagens da sala">
        {snapshot.messages.map(entry => <li key={entry.id}><strong>{entry.name}</strong><p>{entry.text}</p></li>)}
      </ol>
        <form onSubmit={event => { event.preventDefault(); void perform({ kind: 'chat', text: chat }, () => setChat('')); }}>
          <label>Mensagem<textarea aria-label="Mensagem" value={chat} onChange={event => setChat(event.target.value)} maxLength={WORKSPACE_LIMITS.message} disabled={busy} rows={2}/></label>
          <button type="submit" disabled={disabled || !chat.trim()}>Enviar mensagem</button>
        </form>
      </div>
      <div><h3>Nota compartilhada</h3>
        <label>Texto da sala<textarea aria-label="Texto da sala" rows={5} maxLength={WORKSPACE_LIMITS.note} value={draft?.text ?? snapshot.note.text} disabled={busy}
          onChange={event => setDraft(old => ({ text: event.target.value, baseRevision: old?.baseRevision ?? snapshot.note.revision, epoch: old?.epoch ?? snapshot.epoch }))}/></label>
        {draft && (draft.baseRevision !== snapshot.note.revision || draft.epoch !== snapshot.epoch) && <p role="status">A sala mudou enquanto você editava. Seu rascunho foi preservado; copie o que quiser manter antes de carregar a versão atual.</p>}
        <div className="room-tools-actions">
          <button type="button" disabled={disabled || !draft || draft.epoch !== snapshot.epoch || draft.baseRevision !== snapshot.note.revision}
            onClick={() => { if (draft) void perform({ kind: 'note', text: draft.text, baseRevision: draft.baseRevision }, () => setDraft(null)); }}>Salvar nota</button>
          <button type="button" disabled={busy || !draft} onClick={() => setDraft(null)}>Carregar versão da sala</button>
        </div>
        <h3>Tarefas ({snapshot.tasks.length}/{WORKSPACE_LIMITS.tasks})</h3>
        <ul className="room-shared-tasks">{snapshot.tasks.map(item => <li key={item.id}>
          <label><input type="checkbox" checked={pendingTasks[item.id] ?? item.done} disabled={disabled} onChange={event => {
            const next = event.target.checked;
            setPendingTasks(current => ({ ...current, [item.id]: next }));
            void perform({ kind: 'task-set', id: item.id, done: next }).finally(() => {
              setPendingTasks(current => { const copy = { ...current }; delete copy[item.id]; return copy; });
            });
          }}/><span>{item.title}</span></label>
          <button type="button" disabled={disabled} aria-label={`Remover tarefa ${item.title}`} onClick={() => void perform({ kind: 'task-remove', id: item.id })}>Remover</button>
        </li>)}</ul>
        <form onSubmit={event => { event.preventDefault(); void perform({ kind: 'task-add', id: crypto.randomUUID(), title: task }, () => setTask('')); }}>
          <label>Nova tarefa<input aria-label="Nova tarefa" value={task} maxLength={WORKSPACE_LIMITS.title} disabled={busy} onChange={event => setTask(event.target.value)}/></label>
          <button type="submit" disabled={disabled || !task.trim() || snapshot.tasks.length >= WORKSPACE_LIMITS.tasks}>Adicionar tarefa</button>
        </form>
      </div>
    </div>}
  </section>;
}
