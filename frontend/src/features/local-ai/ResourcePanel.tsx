import type { AiState } from './types';
import { pending, statusName } from './types';

function Meter({ label, used, total, limit }: { label: string; used: number | null; total: number | null; limit: number }) {
  const known = used != null && total != null && total > 0;
  const value = known ? Math.min(100, used / total * 100) : 0;
  return <div className="ai-meter">
    <div><strong>{label}</strong><span>{known ? `${used.toFixed(1)} / ${total.toFixed(1)} GiB` : 'Leitura indisponível'}</span></div>
    <div className="ai-meter-track" role="meter" aria-label={`Uso de ${label}`} aria-valuenow={known ? value : undefined} aria-valuemin={0} aria-valuemax={100} aria-valuetext={known ? `${value.toFixed(0)}%` : 'Indisponível'}><i style={{ width: `${value}%`, background: value > limit ? 'var(--danger)' : undefined }} /><b style={{ left: `${limit}%` }} /></div>
    <small>{known ? `Orçamento: ${(total * limit / 100).toFixed(1)} GiB · margem: ${100 - limit}%` : 'A fila aguarda uma medição válida.'}</small>
  </div>;
}
export default function ResourcePanel({ state, busy, cancel, pause }: { state: AiState; busy: boolean; cancel: (id: string) => Promise<unknown>; pause: (value: boolean) => Promise<unknown> }) {
  const waiting = state.jobs.filter(pending);
  return <aside className="glass-panel ai-resources">
    <div className="ai-eyebrow">SEU COMPUTADOR PRIMEIRO</div><h3>Recursos e fila</h3>
    <Meter label="RAM" used={state.resources.ramUsedGb} total={state.resources.ramTotalGb} limit={state.settings.memoryLimitPercent} />
    <Meter label="VRAM" used={state.resources.vramUsedGb} total={state.resources.vramTotalGb} limit={state.settings.memoryLimitPercent} />
    <small>{state.resources.gpuName || 'GPU não identificada'}</small>
    {state.resources.warning && <p className="ai-notice">{state.resources.warning}</p>}
    <button className="btn secondary" disabled={busy} onClick={() => { void pause(!state.paused); }}>{state.paused ? 'Retomar fila' : 'Priorizar meu PC'}</button>
    <p>{state.paused ? 'Fila pausada. Novas tarefas ficam aguardando.' : 'Uma resposta por vez. A próxima só começa quando houver margem.'}</p>
    <h4>{waiting.length} tarefa(s) na fila ou em execução</h4>
    {waiting.map((job, index) => <article className="ai-job" key={job.id}>
      <strong>{index + 1}. {state.chats.find(c => c.id === job.chatId)?.title ?? 'Conversa'}</strong>
      <span>{job.specialist ? `${job.specialist.name} · rodada ${job.round} · ` : ''}{statusName[job.status]}</span><p>{job.detail}</p>
      {job.demand ? <><small>Reserva: {job.demand.ramGb.toFixed(1)} GiB RAM{job.settings.useGpu ? ` · ${job.demand.vramGb.toFixed(1)} GiB VRAM` : ''}</small><small>{job.demand.detail}</small></> : <small>Preparando estimativa de memória…</small>}
      <button className="btn secondary" disabled={busy} onClick={() => { void cancel(job.id); }}>{job.runId ? 'Cancelar reunião' : 'Cancelar tarefa'}</button>
    </article>)}
    {waiting.length === 0 && <p>Nenhum trabalho aguardando. O motor pode manter o modelo carregado após responder.</p>}
    <small>Interromper a resposta não garante liberar imediatamente os pesos do motor externo.</small>
  </aside>;
}
