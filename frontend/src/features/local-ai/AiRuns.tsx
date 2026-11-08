import { useState } from 'react';
import type { AiChat, AiRun } from './types';
import { statusName } from './types';
import type { useLocalAi } from './useLocalAi';

function Review({run,chatId,ai}:{run:AiRun;chatId:string;ai:ReturnType<typeof useLocalAi>}) {
  const [score,setScore]=useState(run.qualityScore??-1),[interventions,setInterventions]=useState(run.interventions),[text,setText]=useState(run.review),[saved,setSaved]=useState(false);
  return <form onSubmit={async e=>{e.preventDefault();setSaved(!!await ai.reviewRun(chatId,run.id,score,interventions,text));}}>
    <fieldset disabled={ai.busy}><legend>Avaliação humana</legend>
      <label>Qualidade verificada<select aria-label="Qualidade verificada" value={score} onChange={e=>{setSaved(false);setScore(Number(e.target.value));}}><option value={-1}>Ainda não avaliada</option>{[0,1,2,3,4,5].map(n=><option value={n} key={n}>{n} / 5</option>)}</select></label>
      <label>Intervenções suas<input type="number" min={0} max={1000} value={interventions} onChange={e=>{setSaved(false);setInterventions(Math.max(0,Math.min(1000,Number(e.target.value))));}}/></label>
      <label>Evidências da avaliação<textarea maxLength={4000} value={text} onChange={e=>{setSaved(false);setText(e.target.value);}} placeholder="O que foi verificado? O que ficou errado ou precisou de correção?"/></label>
      <button className="btn primary" type="submit">Salvar avaliação</button>{saved&&<p role="status">Avaliação salva.</p>}
    </fieldset>
  </form>;
}
export default function AiRuns({chat,ai}:{chat:AiChat;ai:ReturnType<typeof useLocalAi>}) {
  const [selected,setSelected]=useState<string[]>([]);
  const runs=chat.project!.runs;
  const comparison=runs.filter(r=>selected.includes(r.id));
  return <div className="ai-runs"><p>Compare uma execução individual e uma discussão da equipe. Tempo e memória são medidos; qualidade depende da sua verificação. Os deltas de memória são globais e amostrados, incluindo outros aplicativos.</p>
    {comparison.length===2&&<div className="ai-comparison">
      {comparison[0].question!==comparison[1].question&&<p className="ai-notice">As perguntas são diferentes; isso limita a comparação.</p>}
      {comparison[0].planRevision!==comparison[1].planRevision&&<p className="ai-notice">As execuções usaram revisões diferentes do plano.</p>}
      <table><caption>Comparação das execuções selecionadas</caption><thead><tr><th>Medida</th>{comparison.map(r=><th key={r.id}>{r.specialistIds.length===1?'Individual':'Equipe'} · {r.completedTurns} respostas</th>)}</tr></thead>
        <tbody>{[
          ['Geração (s)',...comparison.map(r=>r.generationSeconds.toFixed(1))],
          ['Delta RAM (GiB)',...comparison.map(r=>r.observedRamGb.toFixed(2))],
          ['Delta VRAM (GiB)',...comparison.map(r=>r.observedVramGb.toFixed(2))],
          ['Qualidade / 5',...comparison.map(r=>r.qualityScore??'Não avaliada')],
          ['Intervenções',...comparison.map(r=>r.interventions)]
        ].map(row=><tr key={String(row[0])}>{row.map((cell,i)=><td key={i}>{cell}</td>)}</tr>)}</tbody></table>
    </div>}
    {!runs.length&&<p>As execuções aparecerão aqui depois da primeira pergunta.</p>}
    {[...runs].reverse().map(run=><article className="ai-run" key={run.id}>
      <label className="ai-check"><input type="checkbox" checked={selected.includes(run.id)} disabled={!selected.includes(run.id)&&selected.length>=2} onChange={e=>setSelected(old=>e.target.checked?[...old,run.id]:old.filter(id=>id!==run.id))}/>Comparar execução {run.id.slice(0,8)}</label>
      <strong>{run.purpose==='memory'?'Proposta de memória':run.specialistIds.length===1?'Execução individual':'Discussão da equipe'} · {statusName[run.status]}</strong>
      <p>{run.question}</p><small>{new Date(run.createdAt).toLocaleString()} · plano r{run.planRevision} · {run.rounds} rodada(s) · {run.generationSeconds.toFixed(1)} s de geração</small>
      <p>{run.specialistIds.map(id=>ai.state!.specialists.find(s=>s.id===id)?.name??id).join(' → ')}</p>
      {!['queued','running'].includes(run.status)&&<details><summary>Avaliar resultado {run.qualityScore===null?'':`· ${run.qualityScore}/5`}</summary><Review run={run} chatId={chat.id} ai={ai}/></details>}
    </article>)}
  </div>;
}
