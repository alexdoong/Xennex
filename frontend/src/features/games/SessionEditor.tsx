import { useState } from 'react';
import type { GameMetric, GameSession } from './types';
import type { GameDefinition, SessionContext, SessionEvent } from './definitionTypes';
import { localDate, metricKey } from './types';
import SessionEventsEditor from './SessionEventsEditor';

interface Props { session?: GameSession; definition: GameDefinition; busy: boolean; onSave: (session: GameSession) => Promise<void>; onCancel: () => void }
export default function SessionEditor({ session, definition, busy, onSave, onCancel }: Props) {
  const [title, setTitle] = useState(session?.title ?? '');
  const [date, setDate] = useState(localDate(session?.occurredAt ?? new Date().toISOString()));
  const [patch, setPatch] = useState(session?.patch ?? '');
  const [context, setContext] = useState(session?.context ?? '');
  const [notes, setNotes] = useState(session?.notes ?? '');
  const [contexts, setContexts] = useState<SessionContext[]>(session?.contextValues ?? []);
  const [events, setEvents] = useState<SessionEvent[]>(session?.events ?? []);
  const [metrics, setMetrics] = useState((session?.metrics ?? []).map(m => ({ ...m, value: String(m.value) })));
  const [error, setError] = useState('');
  const available = definition.metrics.filter(m => !m.archived && !metrics.some(current => current.definitionId === m.id));
  const fields = definition.contextFields.filter(c => !c.archived || contexts.some(v => v.definitionId === c.id));
  const submit = async (event: React.SubmitEvent) => {
    event.preventDefault(); setError('');
    const parsed: GameMetric[] = metrics.map(m => ({ ...m, value: Number(m.value.replace(',', '.')) }));
    if (metrics.some(m => !m.value.trim()) || parsed.some(m => !Number.isFinite(m.value))) { setError('Preencha o valor numérico de cada métrica.'); return; }
    if (new Set(parsed.map(metricKey)).size !== parsed.length) { setError('Cada métrica deve aparecer uma vez no registro.'); return; }
    if (!title.trim() || !Number.isFinite(new Date(date).getTime())) { setError('Informe título e data válidos.'); return; }
    if (events.some(e => !Number.isFinite(e.atSeconds) || (e.value !== null && !Number.isFinite(e.value)))) { setError('Confira os tempos e resultados das ações.'); return; }
    const now = new Date().toISOString();
    await onSave({ id: session?.id ?? crypto.randomUUID(), title: title.trim(),
      occurredAt: date === localDate(session?.occurredAt ?? now) && session ? session.occurredAt : new Date(date).toISOString(),
      createdAt: session?.createdAt ?? now, updatedAt: now, patch: patch.trim(), context: context.trim(),
      notes, source: 'manual', metrics: parsed, contextValues: contexts.filter(c => c.value.trim()), events: [...events].sort((a, b) => a.atSeconds - b.atSeconds) });
  };
  return <form className="glass-panel games-editor" onSubmit={submit}>
    <h3>{session ? 'Editar registro' : 'Novo registro'}</h3>
    <fieldset disabled={busy}>
      <div className="games-fields">
        <label>Título<input required maxLength={160} value={title} onChange={e => setTitle(e.target.value)} placeholder="Treino, partida ou experimento" /></label>
        <label>Data e hora local<input required type="datetime-local" value={date} onChange={e => setDate(e.target.value)} /></label>
        <label>Patch / versão<input maxLength={80} value={patch} onChange={e => setPatch(e.target.value)} placeholder="Desconhecido, se não informado" /></label>
        <label>Contexto<input maxLength={400} value={context} onChange={e => setContext(e.target.value)} placeholder="Observação geral da sessão" /></label>
      </div>
      {!!fields.length && <section className="games-definition-section"><h4>Condições deste cenário</h4><div className="games-fields">{fields.map(field => {
        const existing = contexts.find(c => c.definitionId === field.id);
        return <label key={field.id}>{field.name}<input maxLength={400} value={existing?.value ?? ''} placeholder={field.description || 'Não informado'} onChange={e => setContexts([...contexts.filter(c => c.definitionId !== field.id), { definitionId: field.id, name: existing?.name ?? field.name, value: e.target.value }])} /></label>;
      })}</div></section>}
      <label htmlFor="games-session-notes">Notas</label><textarea id="games-session-notes" maxLength={8000} rows={3} value={notes} onChange={e => setNotes(e.target.value)} placeholder="O que testou e o que percebeu?" />
      <div className="games-toolbar"><h4>Métricas definidas para este jogo</h4>
        <button className="btn secondary" type="button" disabled={metrics.length >= 12 || !available.length} onClick={() => { const m = available[0]; setMetrics([...metrics, { definitionId: m.id, name: m.name, value: '', unit: m.unit }]); }}>Adicionar métrica</button></div>
      {!definition.metrics.some(m => !m.archived) && <p className="games-muted">Defina suas métricas em “Definir jogo” para começar a medir.</p>}
      {metrics.map((metric, index) => <div className="games-metric-fields" key={index}>
        <label>Métrica do registro {index + 1}<select aria-label={'Métrica do registro ' + (index + 1)} value={metric.definitionId ?? ''} onChange={e => { const m = definition.metrics.find(m => m.id === e.target.value)!; setMetrics(metrics.map((old, i) => i === index ? { ...old, definitionId: m.id, name: m.name, unit: m.unit } : old)); }}>
          {!metric.definitionId && <option value="">Legado: {metric.name}</option>}
          {definition.metrics.filter(m => m.id === metric.definitionId || (!m.archived && !metrics.some(current => current.definitionId === m.id))).map(m => <option key={m.id} value={m.id}>{m.name}{m.archived ? ' (arquivada)' : ''}</option>)}
        </select></label>
        <label>Valor<input required inputMode="decimal" value={metric.value} onChange={e => setMetrics(metrics.map((m, i) => i === index ? { ...m, value: e.target.value } : m))} placeholder="98,5" /></label>
        <label>Unidade<input readOnly value={metric.unit} /></label>
        <button type="button" className="btn secondary" aria-label={'Remover métrica ' + (index + 1)} onClick={() => setMetrics(metrics.filter((_, i) => i !== index))}>Remover</button>
      </div>)}
      <SessionEventsEditor definition={definition} events={events} onChange={setEvents} />
      {error && <p role="alert">{error}</p>}
      <div className="games-toolbar"><button type="submit" className="btn primary">{busy ? 'Salvando…' : 'Salvar registro'}</button>
        <button type="button" className="btn secondary" onClick={onCancel}>Cancelar</button></div>
    </fieldset>
  </form>;
}
