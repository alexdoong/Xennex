import { useMemo, useState } from 'react';
import type { GameSession } from './types';
import { displayDate, metricKey } from './types';
import ScenarioDetails from './ScenarioDetails';
import ContextComparison from './ContextComparison';

interface Props { sessions: GameSession[]; busy: boolean; onEdit: (session: GameSession) => void }
export default function GameHistory({ sessions, busy, onEdit }: Props) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [query, setQuery] = useState('');
  const [chosenMetric, setChosenMetric] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [source, setSource] = useState<'sessions' | 'events'>('sessions');
  const [contextField, setContextField] = useState('');
  const [contextValue, setContextValue] = useState('');
  const contextDefinitions = [...new Map(sessions.flatMap(s => s.contextValues ?? []).map(c => [c.definitionId, c.name])).entries()];
  const visible = useMemo(() => sessions.filter(s => {
    const date = new Date(s.occurredAt);
    return (!from || date >= new Date(from + 'T00:00:00')) &&
      (!to || date <= new Date(to + 'T23:59:59.999')) &&
      (!contextField || !contextValue || s.contextValues?.some(c => c.definitionId === contextField && c.value.toLocaleLowerCase().includes(contextValue.toLocaleLowerCase()))) &&
      [s.title, s.context, s.patch, s.notes, ...(s.contextValues ?? []).map(c => c.name + ' ' + c.value), ...(s.events ?? []).map(e => e.actionName + ' ' + e.actor)].join(' ').toLocaleLowerCase().includes(query.toLocaleLowerCase());
  }).sort((a, b) => Date.parse(a.occurredAt) - Date.parse(b.occurredAt)), [sessions, from, to, query, contextField, contextValue]);
  const observations = source === 'sessions' ? visible.flatMap(s => s.metrics.map((metric, index) => ({ session: s, metric, time: Date.parse(s.occurredAt), key: s.id + '-' + index }))) :
    visible.flatMap(s => (s.events ?? []).flatMap((event, index) => event.value === null ? [] : [{
      session: s, metric: { definitionId: event.metricId, name: event.metricName, value: event.value, unit: event.unit },
      time: Date.parse(s.occurredAt) + event.atSeconds * 1000, key: s.id + '-event-' + index
    }])).sort((a, b) => a.time - b.time);
  const definitions = [...new Map(observations.map(p => [metricKey(p.metric), p.metric])).entries()];
  const metricId = definitions.some(([key]) => key === chosenMetric) ? chosenMetric : definitions[0]?.[0] ?? '';
  const points = observations.filter(p => metricKey(p.metric) === metricId);
  const values = points.map(p => p.metric.value);
  const low = values.reduce((min, v) => Math.min(min, v), Infinity), high = values.reduce((max, v) => Math.max(max, v), -Infinity);
  const first = points[0]?.time ?? 0, last = points.at(-1)?.time ?? first;
  const xy = points.map(p => ({ ...p,
    x: first === last ? 300 : 30 + (p.time - first) / (last - first) * 540,
    y: high === low ? 80 : 130 - (p.metric.value - low) / (high - low) * 100 }));
  const compared = visible.filter(s => selected.includes(s.id));
  const rows = [...new Map(compared.flatMap(s => s.metrics).map(m => [metricKey(m), m])).entries()];
  return <>
    <div className="glass-panel">
      <h3>Histórico e evolução</h3>
      <div className="games-fields">
        <label>De<input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label>
        <label>Até<input type="date" value={to} onChange={e => setTo(e.target.value)} /></label>
        <label>Buscar contexto ou patch<input value={query} onChange={e => setQuery(e.target.value)} /></label>
        <label>Métrica do gráfico<select value={metricId} onChange={e => setChosenMetric(e.target.value)}>
          {!definitions.length && <option value="">Sem métricas no período</option>}
          {definitions.map(([key, metric]) => <option key={key} value={key}>{metric.name} {metric.unit && '(' + metric.unit + ')'}</option>)}
        </select></label>
      </div>
      <div className="games-fields">
        <label>Origem dos valores<select value={source} onChange={e => setSource(e.target.value as typeof source)}><option value="sessions">Resultados da sessão</option><option value="events">Resultados das ações</option></select></label>
        <label>Agrupar por condição<select value={contextField} onChange={e => { setContextField(e.target.value); setContextValue(''); }}><option value="">Sem agrupamento</option>{contextDefinitions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        {contextField && <label>Filtrar valor da condição<input value={contextValue} onChange={e => setContextValue(e.target.value)} placeholder="Build, equipe ou valor desejado" /></label>}
      </div>
      {from && to && from > to && <p role="alert">A data inicial deve ser anterior à final.</p>}
      {!!points.length && <div className="games-chart">
        <p>{points.length} observações · mínimo {low.toLocaleString('pt-BR')} · máximo {high.toLocaleString('pt-BR')} {points[0].metric.unit}</p>
        <svg viewBox="0 0 600 165" role="img" aria-label={'Evolução de ' + points[0].metric.name}>
          <line x1="30" y1="140" x2="570" y2="140" stroke="currentColor" opacity=".3" />
          {xy.filter((_, i) => i % Math.max(1, Math.ceil(xy.length / 600)) === 0 || i === xy.length - 1).map(p => <circle key={p.key} cx={p.x} cy={p.y} r="5" fill="var(--primary)">
            <title>{displayDate(new Date(p.time).toISOString())}: {p.metric.value} {p.metric.unit} — {p.session.title}</title></circle>)}
        </svg>
        <div className="games-toolbar"><small>{displayDate(new Date(points[0].time).toISOString())}</small><small>{displayDate(new Date(points.at(-1)!.time).toISOString())}</small></div>
        <p className="games-muted">Cada ponto é um registro manual. Contextos e patches diferentes podem alterar a comparação; valor maior não significa necessariamente melhor.</p>
      </div>}
      <ContextComparison points={points} fieldId={contextField} />
      {xy.length > 600 && <p className="games-muted">O gráfico mostra uma amostra dos pontos; o resumo utiliza todas as observações.</p>}
      {visible.length === 0 && <p className="games-muted">{sessions.length ? 'Nenhum registro corresponde aos filtros.' : 'Registre sua primeira sessão para começar o histórico.'}</p>}
      <div className="games-timeline">{[...visible].reverse().map(session => <article key={session.id}>
        <div className="games-toolbar"><h4>{session.title}</h4><small>{displayDate(session.occurredAt)}</small></div>
        <p className="games-muted">{session.context || 'Contexto não informado'} · Patch: {session.patch || 'desconhecido'} · Registro manual</p>
        {!!session.metrics.length && <div className="games-chips">{session.metrics.map(metric => <span key={metricKey(metric)}>{metric.name}: <strong>{metric.value.toLocaleString('pt-BR')} {metric.unit}</strong></span>)}</div>}
        <ScenarioDetails session={session} />
        {session.notes && <p className="games-notes">{session.notes}</p>}
        <div className="games-toolbar">
          <label className="games-check"><input type="checkbox" checked={selected.includes(session.id)}
            disabled={!selected.includes(session.id) && compared.length >= 2}
            onChange={e => setSelected(e.target.checked ? [...compared.map(s => s.id), session.id] : selected.filter(id => id !== session.id))} />Comparar {session.title}</label>
          <button type="button" className="btn secondary" disabled={busy} onClick={() => onEdit(session)}>Editar registro</button>
        </div>
      </article>)}</div>
    </div>
    {compared.length > 0 && <div className="glass-panel games-comparison"><h3>Comparação de registros</h3>
      {compared.length < 2 ? <p>Selecione mais um registro do período para comparar.</p> : <>
        <p className="games-muted">Diferença = segundo registro − primeiro, em ordem cronológica. Dados ausentes aparecem como “—”.</p>
        <div className="games-table-scroll"><table><thead><tr><th>Informação</th>{compared.map(s => <th key={s.id}>{s.title}</th>)}<th>Diferença</th></tr></thead><tbody>
          <tr><th>Data</th>{compared.map(s => <td key={s.id}>{displayDate(s.occurredAt)}</td>)}<td>—</td></tr>
          <tr><th>Contexto</th>{compared.map(s => <td key={s.id}>{s.context || '—'}</td>)}<td>—</td></tr>
          <tr><th>Patch</th>{compared.map(s => <td key={s.id}>{s.patch || 'Desconhecido'}</td>)}<td>—</td></tr>
          {contextDefinitions.map(([id, name]) => <tr key={id}><th>{name}</th>{compared.map(s => <td key={s.id}>{s.contextValues?.find(c => c.definitionId === id)?.value || '—'}</td>)}<td>—</td></tr>)}
          {rows.map(([key, metric]) => {
            const a = compared[0].metrics.find(m => metricKey(m) === key), b = compared[1].metrics.find(m => metricKey(m) === key);
            return <tr key={key}><th>{metric.name} {metric.unit}</th><td>{a?.value.toLocaleString('pt-BR') ?? '—'}</td><td>{b?.value.toLocaleString('pt-BR') ?? '—'}</td><td>{a && b ? (b.value - a.value).toLocaleString('pt-BR', { maximumFractionDigits: 6 }) : '—'}</td></tr>;
          })}
        </tbody></table></div></>}
    </div>}
  </>;
}
