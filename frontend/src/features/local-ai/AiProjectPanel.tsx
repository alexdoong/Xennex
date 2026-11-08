import { useState } from 'react';
import type { AiChat } from './types';
import type { useLocalAi } from './useLocalAi';
import { pending } from './types';
import AiProjectEditor from './AiProjectEditor';
import AiNotebooks from './AiNotebooks';
import { downloadText } from './roomUtils';
import AiRuns from './AiRuns';

export default function AiProjectPanel({chat,ai,source}:{chat:AiChat;ai:ReturnType<typeof useLocalAi>;source:(id:string)=>void}) {
  const [tab,setTab]=useState('Sala'),[editing,setEditing]=useState(false);
  const project=chat.project!;
  const locked=ai.busy||ai.state!.jobs.some(j=>j.chatId===chat.id&&pending(j));
  const plan=project.plans.at(-1);
  return <div className="ai-project-panel">
    <nav aria-label="Áreas da sala">{['Sala','Plano','Cadernos','Execuções'].map(label=><button className={'btn '+(tab===label?'primary':'secondary')} key={label} onClick={()=>setTab(label)}>{label}</button>)}</nav>
    {tab==='Sala'&&<><p>{project.goal||'Defina um objetivo e convide especialistas para começar.'}</p>
      <div className="ai-room-members">{project.members.map(member=>{
        const profile=ai.state!.specialists.find(s=>s.id===member.specialistId)!;
        const job=ai.state!.jobs.find(j=>j.chatId===chat.id&&j.specialist?.id===profile.id&&pending(j));
        return <article key={profile.id}><span className="ai-avatar">{profile.name.slice(0,2).toUpperCase()}</span><div><strong>{profile.name}</strong><small>{profile.role}</small><small>{profile.model||ai.state!.settings.model||'Sem modelo'}</small></div><span>{job?.status==='running'?'Respondendo':job?'Na fila':'Disponível'}</span></article>;
      })}</div><button className="btn secondary" disabled={locked} onClick={()=>setEditing(true)}>Editar plano e membros</button></>}
    {tab==='Plano'&&<><div className="ai-actions"><strong>Plano atual · revisão {plan?.revision??0}</strong><button className="btn secondary" disabled={locked} onClick={()=>setEditing(true)}>Editar plano e membros</button><button className="btn secondary" onClick={()=>downloadText('plano-'+chat.id+'.md',`# ${chat.title}\n\n${project.goal}\n\n${plan?.content??''}`)}>Exportar plano</button></div>
      <pre className="ai-plan-text">{plan?.content||'O plano ainda está vazio.'}</pre>
      <details><summary>Histórico do plano ({project.plans.length} revisões)</summary>{[...project.plans].reverse().map(version=><details key={version.revision}><summary>Revisão {version.revision} · {new Date(version.createdAt).toLocaleString()}</summary><pre>{version.content}</pre></details>)}</details>
    </>}
    {editing&&<AiProjectEditor chat={chat} specialists={ai.state!.specialists} busy={locked} save={ai.saveProject} close={()=>setEditing(false)}/>}
    {tab==='Cadernos'&&<AiNotebooks chat={chat} ai={ai} locked={locked} source={source}/>}
    {tab==='Execuções'&&<AiRuns chat={chat} ai={ai}/>}
  </div>;
}
