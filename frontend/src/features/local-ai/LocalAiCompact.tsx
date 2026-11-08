import { useEffect, useRef } from 'react';
import { Bot, Send, XCircle, Maximize2 } from 'lucide-react';
import { useLocalAiContext } from './LocalAiContext';
import { pending, statusName } from './types';
import type { AppTab } from '../../layout/navigation';

type Props = {
  openFullWindow: (tab?: AppTab) => void;
};

export default function LocalAiCompact({ openFullWindow }: Props) {
  const ai = useLocalAiContext();
  const { selected, setSelected, drafts, setDrafts } = ai;
  const transcript = useRef<HTMLDivElement>(null);

  const state = ai.state;
  const chat = state?.chats.find(c => c.id === selected) ?? state?.chats[0];
  const currentJob = state?.jobs.find(j => j.chatId === chat?.id && pending(j));
  const draft = drafts[chat?.id ?? 'new'] ?? '';
  const lastContent = chat?.messages.find(m => m.status === 'running')?.content ?? chat?.messages.at(-1)?.content;

  useEffect(() => {
    const el = transcript.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lastContent, chat?.messages.length]);

  const send = async () => {
    if (ai.busy || currentJob || !state?.settings.model || !draft.trim() || chat?.project) return;
    const id = chat?.id ?? await ai.newChat();
    if (!id) return;
    setSelected(id);
    if (!chat) setDrafts(old => ({ ...old, [id]: draft }));
    const result = await ai.send(id, draft);
    if (result) {
      setDrafts(old => ({
        ...old,
        [id]: old[id] === draft ? '' : old[id] ?? '',
        ...(!chat ? { new: '' } : {})
      }));
    }
  };


  return (
    <div className="compact-module-view compact-local-ai">
      {state && state.chats.length > 0 && (
        <div className="compact-chat-picker">
          <label htmlFor="compact-chat-select">Conversa</label>
          <select
            id="compact-chat-select"
            value={chat?.id ?? ''}
            onChange={e => setSelected(e.target.value)}
          >
            {state.chats.map(c => (
              <option key={c.id} value={c.id}>
                {c.project ? '📁 ' : '💬 '}{c.title}
              </option>
            ))}
          </select>
        </div>
      )}

      {ai.error && <p role="alert" className="compact-error">{ai.error}</p>}
      {state?.warning && <p role="alert" className="compact-error">{state.warning}</p>}

      <div className="compact-ai-transcript" ref={transcript}>
        {!chat?.messages?.length ? (
          <div className="compact-empty">
            <Bot size={28} />
            <p>Envie uma mensagem para começar a pensar e produzir com sua IA local.</p>
          </div>
        ) : (
          chat.messages.slice(-20).map(msg => (
            <article key={msg.id} className={`compact-ai-msg ${msg.role}`}>
              <div className="compact-ai-msg-meta">
                <strong>{msg.role === 'user' ? 'Você' : (msg.authorName || 'IA')}</strong>
                <small>{statusName[msg.status] ?? msg.status}</small>
              </div>
              <pre>{msg.content || (msg.status === 'queued' ? 'Na fila…' : 'Pensando…')}</pre>
            </article>
          ))
        )}
      </div>

      {currentJob && (
        <div className="compact-job-status" role="status">
          <span>{currentJob.detail || 'Executando…'}</span>
          <button
            className="btn secondary btn-sm"
            onClick={() => void ai.cancel(currentJob.id)}
            title="Cancelar"
          >
            <XCircle size={14} /> Cancelar
          </button>
        </div>
      )}

      {chat?.project ? <p className="compact-hint">Esta é uma sala de especialistas. Expanda para escolher os participantes e iniciar uma rodada.</p> : <form
        className="compact-ai-composer"
        onSubmit={e => { e.preventDefault(); void send(); }}
      >
        <textarea
          rows={2}
          maxLength={16000}
          aria-label="Mensagem compacta"
          value={draft}
          placeholder="Escreva sua mensagem…"
          disabled={ai.busy}
          onChange={e => setDrafts(old => ({ ...old, [chat?.id ?? 'new']: e.target.value }))}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button
          type="submit"
          className="btn primary compact-send-btn"
          disabled={ai.busy || !!currentJob || !state?.settings.model || !draft.trim()}
          title="Enviar"
        >
          <Send size={15} />
        </button>
      </form>}

      <button
        className="compact-expand-link"
        onClick={() => openFullWindow('local-ai')}
      >
        <Maximize2 size={13} />
        <span>Abrir salas de projeto e especialistas completos</span>
      </button>
    </div>
  );
}
