import { useState } from 'react';
import type { AiChat, AiMember, AiProjectEdit, AiSpecialist } from './types';
interface Props { chat: AiChat; specialists: AiSpecialist[]; busy: boolean; save:(id:string,project:AiProjectEdit)=>Promise<boolean|undefined>; close:()=>void }
export default function AiProjectEditor({chat,specialists,busy,save,close}:Props) {
  const [draft,setDraft]=useState<AiProjectEdit>(()=>({revision:chat.project?.revision??0,title:chat.title,goal:chat.project?.goal??'',plan:chat.project?.plans.at(-1)?.content??'',members:chat.project?.members.map(m=>({...m}))??[]}));
  const toggle=(id:string)=>setDraft(old=>({...old,members:old.members.some(m=>m.specialistId===id)?old.members.filter(m=>m.specialistId!==id):[...old.members,{specialistId:id,sharePlan:true,shareHistory:true,shareNotebook:true}]}));
  const permission=(id:string,key:keyof AiMember,value:boolean)=>setDraft(old=>({...old,members:old.members.map(m=>m.specialistId===id?{...m,[key]:value}:m)}));
  return <form className="ai-project-editor" onSubmit={async e=>{e.preventDefault(); if(await save(chat.id,draft))close();}}>
    <fieldset disabled={busy}><legend>Plano e membros da sala</legend>
      <label>Nome da sala<input required maxLength={160} value={draft.title} onChange={e=>setDraft({...draft,title:e.target.value})}/></label>
      <label>Objetivo do projeto<textarea maxLength={2000} value={draft.goal} onChange={e=>setDraft({...draft,goal:e.target.value})}/></label>
      <label>Plano geral (Markdown)<textarea className="ai-document-input" maxLength={12000} value={draft.plan} onChange={e=>setDraft({...draft,plan:e.target.value})}/></label>
      <p>Convide até oito especialistas. As permissões abaixo controlam o que será enviado ao modelo local, além da pergunta atual. Um membro presente não mantém um modelo carregado.</p>
      {!specialists.length && <p>Cadastre perfis em Especialistas para convidar seu time.</p>}
      {specialists.map(profile=>{
        const member=draft.members.find(m=>m.specialistId===profile.id);
        return <div className="ai-member-edit" key={profile.id}>
          <label className="ai-check"><input type="checkbox" checked={!!member} disabled={!member&&draft.members.length>=8} onChange={()=>toggle(profile.id)}/>{profile.name} · {profile.role}</label>
          {member&&<div className="ai-permissions">{([['sharePlan','Plano e objetivo'],['shareHistory','Histórico e discussão'],['shareNotebook','Próprio caderno']] as const).map(([key,label])=><label className="ai-check" key={key}><input type="checkbox" checked={member[key]} onChange={e=>permission(profile.id,key,e.target.checked)}/>{label}</label>)}</div>}
        </div>;
      })}
      <p className="ai-notice">Esta etapa não concede acesso a arquivos externos, terminal, internet ou serviços pagos. Pedidos dos especialistas aparecem como texto para sua revisão.</p>
      <div className="ai-actions"><button className="btn secondary" type="button" onClick={close}>Cancelar edição</button><button className="btn primary" type="submit">Salvar sala</button></div>
    </fieldset>
  </form>;
}
