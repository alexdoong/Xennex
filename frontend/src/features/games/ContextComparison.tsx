import type { GameSession } from './types';

interface Point { session: GameSession; metric: { value: number; unit: string } }
export default function ContextComparison({ points, fieldId }: { points: Point[]; fieldId: string }) {
  if (!fieldId || !points.length) return null;
  const groups = new Map<string, { count: number; sum: number; min: number; max: number }>();
  for (const point of points) {
    const key = point.session.contextValues?.find(c => c.definitionId === fieldId)?.value || 'Não informado';
    const group = groups.get(key) ?? { count: 0, sum: 0, min: Infinity, max: -Infinity };
    group.count++; group.sum += point.metric.value;
    group.min = Math.min(group.min, point.metric.value); group.max = Math.max(group.max, point.metric.value);
    groups.set(key, group);
  }
  return <div className="games-table-scroll"><h4>Resultados por condição</h4><p className="games-muted">Resumo das observações filtradas; compare também patch e outras condições.</p>
    <table><thead><tr><th>Condição</th><th>Observações</th><th>Média</th><th>Mínimo</th><th>Máximo</th></tr></thead><tbody>{[...groups].map(([key, group]) => <tr key={key}>
      <th>{key}</th><td>{group.count}</td><td>{(group.sum / group.count).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} {points[0].metric.unit}</td>
      <td>{group.min.toLocaleString('pt-BR')}</td><td>{group.max.toLocaleString('pt-BR')}</td>
    </tr>)}</tbody></table>
  </div>;
}
