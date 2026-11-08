import { useState } from 'react';
import type { AiChat, AiNote } from './types';
import type { useLocalAi } from './useLocalAi';

import { noteStatus, downloadText } from './roomUtils';
export default function AiNotebooks({chat,ai,locked,source}: {chat:AiChat;ai:ReturnType<typeof useLocalAi>;locked:boolean;source:(id:string)=>void}) {
  const project=chat.project!;
  const [selected,setSelected]=useState('');
  const [learningFocus,setLearningFocus]=useState('');
  const member=project.members.find(m=>m.specialistId===selected)??project.members[0];
  const [draft,setDraft]=useState<{note:AiNote;revision:number}|null>(null);
  const profile=ai.state!.specialists.find(s=>s.id===member?.specialistId);
  const notes=project.notes.filter(n=>n.specialistId===profile?.id);
  const startNote=(note?:AiNote)=>{
    if(!profile)return;
    const now=new Date().toISOString();
    setDraft({revision:project.revision,note:note?{...note,sourceMessageIds:[...note.sourceMessageIds]}:{id:crypto.randomUUID().replaceAll('-',''),specialistId:profile.id,content:'',status:'hypothesis',origin:'user',sourceMessageIds:[],createdAt:now,updatedAt:now}});
  };
  return <div className="ai-notebooks">
    <p>Um caderno por especialista nesta sala. Só notas confirmadas ou hipóteses podem entrar no contexto; propostas aguardam sua revisão. Cadernos de outros especialistas não são enviados diretamente; suas respostas na discussão podem conter trechos deles.</p>
    <label>Caderno do especialista<select aria-label="Caderno do especialista" disabled={!!draft} value={profile?.id??''} onChange={e=>setSelected(e.target.value)}>
      {!profile&&<option value="">Convide um especialista</option>}
      {project.members.map(m=><option key={m.specialistId} value={m.specialistId}>{ai.state!.specialists.find(s=>s.id===m.specialistId)?.name}</option>)}
    </select></label>
    {profile&&<label>Orientar aprendizado (opcional)<textarea maxLength={1000} disabled={locked||!!draft} value={learningFocus} onChange={e=>setLearningFocus(e.target.value)} placeholder="Ex.: minhas preferências de resposta, correções que fiz ou como você entendeu o projeto."/></label>}
    {profile&&<p>Para aprender com a conversa, peça uma proposta abaixo e revise o que deve ser lembrado. Depois de confirmada, a nota pode orientar novas respostas.</p>}
    {profile&&<div className="ai-actions">
      <button className="btn secondary" disabled={locked||!!draft} onClick={()=>startNote()}>Nova nota</button>
      <button className="btn secondary" disabled={locked||!!draft} onClick={()=>void ai.runProject(chat.id,{requestId:crypto.randomUUID(),question:'Revise a conversa disponível: preferências explícitas do usuário, correções, decisões e dúvidas. Proponha uma nota para orientar seu trabalho futuro, separando evidências de interpretações. Não invente aprendizados.'+(learningFocus.trim()?' Foco solicitado: '+learningFocus.trim():''),purpose:'memory',rounds:1,specialistIds:[profile.id]})}>Propor memória</button>
      <button className="btn secondary" disabled={ai.busy} onClick={async()=>{const text=await ai.exportNotebook(chat.id,profile.id);if(text!==undefined)downloadText('caderno-'+profile.id+'.md',text);}}>Exportar Markdown</button>
    </div>}
    {draft&&<form onSubmit={async e=>{e.preventDefault();if(await ai.saveNote(chat.id,draft.revision,draft.note))setDraft(null);}}>
      <fieldset disabled={locked}><legend>Revisar nota</legend>
        <label>Conteúdo da nota (Markdown)<textarea required maxLength={12000} className="ai-document-input" value={draft.note.content} onChange={e=>setDraft({...draft,note:{...draft.note,content:e.target.value}})}/></label>
        <label>Estado da nota<select aria-label="Estado da nota" value={draft.note.status} onChange={e=>setDraft({...draft,note:{...draft.note,status:e.target.value as AiNote['status']}})}>{Object.entries(noteStatus).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
        <label>Vincular mensagem como evidência<select aria-label="Vincular mensagem como evidência" value="" onChange={e=>{if(e.target.value)setDraft({...draft,note:{...draft.note,sourceMessageIds:[...new Set([...draft.note.sourceMessageIds,e.target.value])].slice(0,32)}});}}>
          <option value="">Selecione uma mensagem…</option>{chat.messages.filter(m=>m.status==='complete').slice(-100).map(m=><option key={m.id} value={m.id}>{m.authorName||'Você'}: {m.content.slice(0,90)}</option>)}
        </select></label>
        <div className="ai-note-sources">{draft.note.sourceMessageIds.map(id=><button type="button" className="btn secondary" key={id} onClick={()=>setDraft({...draft,note:{...draft.note,sourceMessageIds:draft.note.sourceMessageIds.filter(s=>s!==id)}})}>Remover fonte {id.slice(0,8)}</button>)}</div>
        <div className="ai-actions"><button className="btn secondary" type="button" onClick={()=>setDraft(null)}>Cancelar nota</button><button className="btn primary" type="submit">Salvar nota revisada</button></div>
      </fieldset>
    </form>}
    {!notes.length&&!draft&&<p>O caderno está vazio. Registre interpretações, evidências e perguntas que devem sobreviver à conversa.</p>}
    {notes.map(note=><article className="ai-note" key={note.id}><div className="ai-actions"><strong>{noteStatus[note.status]}</strong><button className="btn secondary" disabled={locked||!!draft} onClick={()=>startNote(note)}>Revisar nota</button></div>
      <small>{note.origin} · {new Date(note.updatedAt).toLocaleString()}</small><pre>{note.content}</pre>
      <div className="ai-note-sources">{note.sourceMessageIds.map(id=><button className="btn secondary" key={id} onClick={()=>source(id)}>Ver fonte {id.slice(0,8)}</button>)}</div>
    </article>)}
  </div>;
}
