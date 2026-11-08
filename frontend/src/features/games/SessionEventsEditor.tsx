import type { GameDefinition, SessionEvent } from './definitionTypes';

interface Props { definition: GameDefinition; events: SessionEvent[]; onChange: (events: SessionEvent[]) => void }
export default function SessionEventsEditor({ definition, events, onChange }: Props) {
  const actions = definition.actions.filter(a => !a.archived);
  const patch = (index: number, value: Partial<SessionEvent>) => onChange(events.map((e, i) => i === index ? { ...e, ...value } : e));
  return <section className="games-definition-section"><div className="games-toolbar"><h4>Sequência de ações</h4><button type="button" className="btn secondary" disabled={!actions.length || events.length >= 120} onClick={() => onChange([...events, {
    actionId: actions[0].id, actionName: actions[0].name, actor: '', atSeconds: events.at(-1)?.atSeconds ?? 0,
    metricId: '', metricName: '', value: null, unit: '', notes: ''
  }])}>Registrar ação</button></div>
    {!actions.length && <p className="games-muted">Cadastre ações em “Definir jogo” para registrar uma rotação ou sequência.</p>}
    {events.map((event, index) => <div className="games-event-editor" key={index}>
      <div className="games-fields">
        <label>Ação {index + 1}<select aria-label={'Ação ' + (index + 1)} value={event.actionId} onChange={e => { const action = definition.actions.find(a => a.id === e.target.value)!; patch(index, { actionId: action.id, actionName: action.name }); }}>{definition.actions.filter(a => !a.archived || a.id === event.actionId).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>Tempo em segundos {index + 1}<input required type="number" min="0" max="604800" step="any" value={event.atSeconds} onChange={e => patch(index, { atSeconds: e.target.valueAsNumber })} /></label>
        <label>Quem / qual peça {index + 1}<input maxLength={100} value={event.actor} onChange={e => patch(index, { actor: e.target.value })} placeholder="Personagem, carta, jogador…" /></label>
        <label>Resultado medido {index + 1}<select aria-label={'Resultado medido ' + (index + 1)} value={event.metricId} onChange={e => { const metric = definition.metrics.find(m => m.id === e.target.value); patch(index, { metricId: metric?.id ?? '', metricName: metric?.name ?? '', unit: metric?.unit ?? '', value: null }); }}><option value="">Sem resultado numérico</option>{definition.metrics.filter(m => !m.archived || m.id === event.metricId).map(m => <option key={m.id} value={m.id}>{m.name} ({m.unit || 'valor'})</option>)}</select></label>
        {event.metricId && <label>Valor do resultado {index + 1} ({event.unit})<input type="number" step="any" min="-1000000000000000" max="1000000000000000" value={event.value ?? ''} onChange={e => patch(index, { value: e.target.value === '' ? null : e.target.valueAsNumber })} /></label>}
        <label>Detalhes da ação {index + 1}<input maxLength={2000} value={event.notes} onChange={e => patch(index, { notes: e.target.value })} placeholder="Buff ativo, motivo da troca, condição…" /></label>
      </div>
      <button type="button" className="btn secondary" onClick={() => onChange(events.filter((_, i) => i !== index))}>Remover ação {index + 1}</button>
    </div>)}
  </section>;
}
