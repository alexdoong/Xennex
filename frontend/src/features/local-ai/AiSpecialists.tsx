import { useState } from 'react';
import type { AiSpecialist } from './types';
import type { useLocalAi } from './useLocalAi';

const newProfile = (): AiSpecialist => ({id:crypto.randomUUID().replaceAll('-',''),revision:0,name:'',role:'',model:'',instructions:''});
export default function AiSpecialists({ ai }: { ai: ReturnType<typeof useLocalAi> }) {
  const [profile,setProfile] = useState<AiSpecialist>(newProfile);
  const locked = ai.busy || ai.state!.jobs.some(j=>j.status==='queued'||j.status==='running');
  return <section className="glass-panel ai-specialists" aria-label="Catálogo de especialistas">
    <div><h3>Seu time local</h3><p>Cada perfil tem identidade, instruções e modelo. Vários perfis podem usar os mesmos pesos; criar um perfil não treina nem baixa um modelo.</p>
      <div className="ai-profile-list">{ai.state!.specialists.map(item=><button className="btn secondary" key={item.id} disabled={locked} onClick={()=>setProfile({...item})}><strong>{item.name}</strong><small>{item.role} · {item.model || 'modelo global'}</small></button>)}</div>
      <button className="btn secondary" disabled={locked} onClick={()=>setProfile(newProfile())}>Novo perfil</button>
      <button className="btn secondary" disabled={locked} onClick={()=>{void ai.discover();}}>Atualizar modelos instalados</button>
    </div>
    <form onSubmit={async e=>{e.preventDefault(); if(await ai.saveSpecialist(profile))setProfile(newProfile());}}>
      <fieldset disabled={locked}><legend>{profile.revision ? 'Editar especialista' : 'Cadastrar especialista'}</legend>
        <label>Nome do especialista<input required maxLength={60} value={profile.name} onChange={e=>setProfile({...profile,name:e.target.value})}/></label>
        <label>Papel / especialidade<input required maxLength={120} value={profile.role} placeholder="Ex.: revisão de código, áudio, planejamento" onChange={e=>setProfile({...profile,role:e.target.value})}/></label>
        <label>Modelo do especialista<input maxLength={200} list="ai-specialist-models" value={profile.model} placeholder="Vazio: usa o modelo da conexão" onChange={e=>setProfile({...profile,model:e.target.value})}/></label>
        <datalist id="ai-specialist-models">{ai.models.map(model=><option key={model} value={model}/>)}</datalist>
        <label>Instruções do especialista<textarea maxLength={4000} value={profile.instructions} placeholder="Como deve trabalhar, limites e critérios de qualidade." onChange={e=>setProfile({...profile,instructions:e.target.value})}/></label>
        <button className="btn primary" type="submit">Salvar especialista</button>
      </fieldset>
    </form>
  </section>;
}
