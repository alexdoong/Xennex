import { useState } from 'react';
import type { GameSession } from './types';
export default function ScenarioDetails({ session }: { session: GameSession }) {
  const [open, setOpen] = useState(false);
  return <>
    {!!session.contextValues?.length && <div className="games-chips">{session.contextValues.map(context => <span key={context.definitionId}>{context.name}: <strong>{context.value}</strong></span>)}</div>}
    {!!session.events?.length && <details className="games-event-history" onToggle={e => setOpen(e.currentTarget.open)}><summary>Sequência registrada · {session.events.length} ações</summary>{open && <ol>{[...session.events].sort((a, b) => a.atSeconds - b.atSeconds).map((event, index) => <li key={index}>
      <time>{event.atSeconds.toLocaleString('pt-BR')}s</time><div><strong>{event.actionName}</strong>{event.actor && <span> · {event.actor}</span>}
        {event.value !== null && <p>{event.metricName}: {event.value.toLocaleString('pt-BR')} {event.unit}</p>}
        {event.notes && <p className="games-muted">{event.notes}</p>}
      </div>
    </li>)}</ol>}</details>}
  </>;
}
