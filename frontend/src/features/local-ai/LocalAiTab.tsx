import { useEffect, useRef, useState } from 'react';
import { Bot, MessageSquarePlus, Settings2, Download } from 'lucide-react';
import { useLocalAiContext } from './LocalAiContext';
import { pending, statusName } from './types';
import AiSettingsPanel from './AiSettingsPanel';
import ResourcePanel from './ResourcePanel';
import AiSpecialists from './AiSpecialists';
import AiProjectPanel from './AiProjectPanel';
import AiRoomComposer from './AiRoomComposer';
import AiProjectEditor from './AiProjectEditor';
import AlicePanel from './AlicePanel';

export default function LocalAiTab({ active: _active }: { active?: boolean }) {
  const ai = useLocalAiContext();
  const { selected, setSelected, drafts, setDrafts } = ai;
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [aliceOpen, setAliceOpen] = useState(false);
  const [aliceOpened, setAliceOpened] = useState(false);
  const [specialistsOpen,setSpecialistsOpen] = useState(false);
  const [projectTitle,setProjectTitle] = useState('');
  const [creatingProject,setCreatingProject] = useState(false);
  const [converting,setConverting] = useState(false);
  const [search,setSearch] = useState('');
  const [visibleCount,setVisibleCount] = useState(60);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const transcript = useRef<HTMLDivElement>(null);
  const state = ai.state;
  const chat = state?.chats.find(c => c.id === selected) ?? state?.chats[0];
  const currentJob = state?.jobs.find(j => j.chatId === chat?.id && pending(j));
  const draft = drafts[chat?.id ?? 'new'] ?? '';
  const filtered = chat?.messages.filter(m => !search || (m.id+' '+m.authorName+' '+m.content).toLocaleLowerCase().includes(search.toLocaleLowerCase())) ?? [];
  const visibleMessages = filtered.slice(-visibleCount);
  const lastContent = chat?.messages.find(m=>m.status==='running')?.content ?? chat?.messages.at(-1)?.content;
  useEffect(() => { setConfirmDelete(false); setConverting(false); setSearch(''); setVisibleCount(60); }, [chat?.id]);
  useEffect(() => {
    const element = transcript.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 160) element.scrollTop = element.scrollHeight;
  }, [lastContent]);
  const send = async () => {
    const id = chat?.id ?? await ai.newChat();
    if (!id) return;
    setSelected(id);
    if (!chat) setDrafts(old => ({ ...old, [id]: draft }));
    const result = await ai.send(id, draft);
    if (result) setDrafts(old => ({ ...old, [id]: old[id] === draft ? '' : old[id] ?? '', ...(!chat ? { new: '' } : {}) }));
  };
  const exportChat = () => {
    if (!chat) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(chat, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `xennex-conversa-${chat.id}.json`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="tab-content local-ai-tab">
    <header className="ai-header"><div><div className="ai-eyebrow">UM ESPAÇO PARA PENSAR E PRODUZIR</div><h2><Bot size={27} /> IA local</h2><p>Suas conversas no seu computador, com espaço para o que você está fazendo.</p></div><div className="ai-actions"><button className="btn secondary" onClick={()=>setSpecialistsOpen(value=>!value)} aria-expanded={specialistsOpen}>Especialistas</button><button className="btn secondary" onClick={() => setSettingsOpen(value => !value)} aria-expanded={settingsOpen}><Settings2 size={16} /> Conexão e orçamento</button></div></header>
    <button className="btn secondary" aria-expanded={aliceOpen} onClick={() => { setAliceOpened(true); setAliceOpen(value => !value); }}>Alice experimental</button>
    {aliceOpened && <div hidden={!aliceOpen}><AlicePanel active={aliceOpen && _active !== false} /></div>}
    {ai.error && <p role="alert" className="ai-error">{ai.error}</p>}
    {state?.warning && <p role="alert" className="ai-error">{state.warning}</p>}
    {!state && !ai.error && <p>Carregando seu espaço local…</p>}
    {state && <>
      {specialistsOpen && <AiSpecialists ai={ai}/>}
      {settingsOpen && <AiSettingsPanel settings={state.settings} models={ai.models} busy={ai.busy} locked={state.jobs.some(pending)} save={ai.save} discover={ai.discover} runtime={ai.runtime} detectRuntime={ai.detectRuntime} startRuntime={ai.startRuntime} releaseModel={ai.releaseModel} />}
      {!state.settings.model && <div className="ai-notice">Conecte um motor e selecione um modelo em “Conexão e orçamento” para começar. As salas podem usar o modelo global ou um modelo diferente por especialista.</div>}
      <div className="ai-workspace">
        <aside className="glass-panel ai-library"><button className="btn primary" disabled={ai.busy} onClick={async () => { const id = await ai.newChat(); if (id) setSelected(id); }}><MessageSquarePlus size={16} /> Nova conversa</button>
          <button className="btn secondary" disabled={ai.busy} onClick={()=>setCreatingProject(value=>!value)}>Nova sala de projeto</button>
          {creatingProject&&<form onSubmit={async e=>{e.preventDefault();const id=await ai.newProject(projectTitle);if(id){setSelected(id);setCreatingProject(false);setProjectTitle('');}}}><label>Nome do novo projeto<input required maxLength={160} value={projectTitle} onChange={e=>setProjectTitle(e.target.value)}/></label><button className="btn primary" disabled={ai.busy||!projectTitle.trim()} type="submit">Criar sala</button></form>}
          <h3>Conversas e projetos</h3>
          {state.chats.map(item => <button className={`ai-chat-link ${chat?.id === item.id ? 'selected' : ''}`} aria-current={chat?.id === item.id ? 'page' : undefined} key={item.id} onClick={() => setSelected(item.id)}><strong>{item.title}</strong><small>{item.project ? "Sala · " : ""}{item.messages.length} mensagens</small></button>)}
          {state.chats.length === 0 && <p>Seu histórico aparecerá aqui.</p>}
        </aside>
        <section className="glass-panel ai-conversation"><div className="ai-conversation-title"><div><h3>{chat?.title ?? 'Comece uma conversa'}</h3><small>{chat?.model || state.settings.model || 'Nenhum modelo selecionado'}</small></div>{chat && <button className="btn secondary" onClick={exportChat} title="Exportar conversa"><Download size={16} /></button>}</div>
          {chat?.project&&<AiProjectPanel key={chat.id} chat={chat} ai={ai} source={id=>{setSearch(id);transcript.current?.scrollIntoView({block:'nearest'});}}/>}
          {chat&&!chat.project&&<button className="btn secondary" disabled={ai.busy||!!currentJob} onClick={()=>setConverting(true)}>Transformar em sala de projeto</button>}
          {converting&&chat&&!chat.project&&<AiProjectEditor chat={chat} specialists={state.specialists} busy={ai.busy||!!currentJob} save={ai.saveProject} close={()=>setConverting(false)}/>}
          {!!chat?.messages.length&&<label>Buscar no histórico<input value={search} onChange={e=>{setSearch(e.target.value);setVisibleCount(60);}} placeholder="Texto, especialista ou identificador da fonte"/></label>}
          <div className="ai-transcript" ref={transcript}>
            {filtered.length>visibleCount&&<button className="btn secondary" onClick={()=>setVisibleCount(n=>n+60)}>Mostrar mensagens anteriores ({filtered.length-visibleCount})</button>}
            {!chat?.messages.length && <div className="ai-empty"><Bot size={44} /><h3>O que vamos explorar?</h3><p>Converse, organize uma ideia ou peça ajuda com um trecho de código. Configure uma sala para discutir com especialistas. Arquivos externos e execução de ações ainda não estão conectados.</p>{!chat?.project&&<div className="ai-suggestions">{['Me ajude a organizar uma ideia', 'Explique um conceito de áudio', 'Revise um trecho de código'].map(text => <button className="btn secondary" key={text} onClick={() => setDrafts(old => ({ ...old, [chat?.id ?? 'new']: text }))}>{text}</button>)}</div>}</div>}
            {visibleMessages.map((message) => <article className={`ai-message ${message.role}`} key={message.id}><div><strong>{message.role === 'user' ? 'Você' : message.authorName || 'Assistente local'}</strong><small>{statusName[message.status] ?? message.status}</small></div>{message.authorId&&<small>{message.authorRole} · {message.model}{message.purpose==='memory' ? ' · proposta de memória' : ''}</small>}<pre>{message.content || (message.status === 'queued' ? 'Aguardando sua vez…' : message.status === 'running' ? 'Preparando a resposta…' : 'Nenhum texto recebido.')}</pre>{message.context&&<details className="ai-context"><summary>Contexto usado · {message.context.omittedMessages} mensagens fora desta janela</summary><small>{message.context.estimatedBytes} bytes estimados de entrada; não é contagem exata de tokens.</small>{!!message.context.excerptMessageIds?.length&&<p>{message.context.excerptMessageIds.length} mensagens incluídas como trechos; o texto integral permanece no histórico.</p>}<ul>{message.context.sources.map(item=><li key={item}>{item}</li>)}</ul></details>}{message.detail && message.status !== 'complete' && <p className="ai-notice">{message.detail}</p>}</article>)}
          </div>
          {currentJob && <p className="ai-notice" role="status">{currentJob.detail}</p>}
          {chat?.project ? <AiRoomComposer key={chat.id} chat={chat} specialists={state.specialists} busy={ai.busy||!!currentJob} run={ai.runProject}/> : <form className="ai-composer" onSubmit={event => { event.preventDefault(); void send(); }}><label htmlFor="ai-prompt">Mensagem</label><textarea disabled={ai.busy} id="ai-prompt" value={draft} maxLength={16000} onChange={e => setDrafts(old => ({ ...old, [chat?.id ?? 'new']: e.target.value }))} placeholder="Escreva sua mensagem…" rows={3} /><div><small>Enter cria uma linha · envio pelo botão</small><button type="submit" className="btn primary" disabled={ai.busy || !!currentJob || !state.settings.model || !draft.trim()}>Enviar</button></div></form>}
          {chat && <div className="ai-delete">{confirmDelete ? <><span>{chat.project ? "Remover esta sala, plano, cadernos e histórico?" : "Remover esta conversa do histórico?"}</span><button className="btn secondary" disabled={ai.busy} onClick={() => { void ai.remove(chat.id); }}>Confirmar remoção</button><button className="btn secondary" onClick={() => setConfirmDelete(false)}>Manter</button></> : <button className="btn secondary" disabled={!!currentJob} onClick={() => setConfirmDelete(true)}>Remover conversa</button>}</div>}
        </section>
        <ResourcePanel state={state} busy={ai.busy} cancel={ai.cancel} pause={ai.pause} />
      </div>
    </>}
  </div>;
}
