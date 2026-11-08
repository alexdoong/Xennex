import { useState } from 'react';
import type { AiChat, AiRunRequest, AiSpecialist } from './types';
interface Props { chat:AiChat; specialists:AiSpecialist[]; busy:boolean; run:(id:string,request:AiRunRequest)=>Promise<string|undefined> }
export default function AiRoomComposer({chat,specialists,busy,run}:Props) {
  const [question,setQuestion]=useState('');
  const [selection,setSelection]=useState<string[]>([]);
  const [rounds,setRounds]=useState(1);
  const members=chat.project!.members;
  const chosen=selection.filter(id=>members.some(m=>m.specialistId===id));
  return <form className="ai-composer ai-room-composer" onSubmit={async e=>{
    e.preventDefault();
    const id=await run(chat.id,{requestId:crypto.randomUUID(),question,purpose:'discussion',rounds,specialistIds:chosen});
    if(id)setQuestion('');
  }}>
    <fieldset disabled={busy}><legend>Próxima rodada</legend>
      <div className="ai-member-selection">{members.map(member=>{
        const profile=specialists.find(p=>p.id===member.specialistId)!;
        return <label className="ai-check" key={profile.id}><input type="checkbox" checked={chosen.includes(profile.id)} onChange={e=>setSelection(old=>e.target.checked?[...old,profile.id]:old.filter(id=>id!==profile.id))}/>{profile.name}</label>;
      })}</div>
      <div className="ai-actions"><button type="button" className="btn secondary" onClick={()=>setSelection(members.map(m=>m.specialistId))}>Selecionar equipe</button>
        <label>Rodadas<select aria-label="Rodadas" value={rounds} onChange={e=>setRounds(Number(e.target.value))}><option value={1}>1 rodada</option><option value={2}>2 rodadas</option><option value={3}>3 rodadas</option></select></label></div>
      <label>Pergunta para a sala<textarea maxLength={16000} required value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Defina o que deseja discutir e os critérios de uma boa resposta."/></label>
      <div><small>{chosen.length*rounds} respostas previstas · execução sequencial · limite de 12</small>
        <button className="btn primary" type="submit" disabled={!chosen.length||chosen.length*rounds>12||!question.trim()}>Iniciar discussão</button></div>
    </fieldset>
  </form>;
}
