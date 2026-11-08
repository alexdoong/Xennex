import CapturePipelineDiagnostics from './CapturePipelineDiagnostics';
import { useCallback, useEffect, useState } from 'react';
import { Radio, Link, Copy, LogIn, Plus, ScreenShare, Square, Users, LogOut, Monitor, ExternalLink, Activity } from 'lucide-react';
import { useStreamContext } from './StreamContext';
import CaptureProgress from './CaptureProgress';
import { nativeApi } from './capture';
import StreamCapturePanel from './StreamCapturePanel';
import TurnFallbackPanel from './TurnFallbackPanel';
import type { VideoReading } from './streamStats';
import type { Quality } from './quality';
import { displayName, PROTOCOL, MAX_PARTICIPANTS, MAX_WATCHING, newRoomCode, normalizeRoom, roomLink } from './protocol';
import { HAS_TURN } from './peerConfig';
import StreamStage from './StreamStage';
import RoomDiagnostics from './RoomDiagnostics';
import RoomEntryDiagnostic from './RoomEntryDiagnostic';
import RoomToolsPanel from './RoomToolsPanel';
import { entryReport } from './entryDiagnostics';
import './stream-workspace.css';

export default function StreamWorkspace({ initialRoom = '', standalone = false }: { initialRoom?: string; standalone?: boolean }) {
  const room = useStreamContext(); const { state, client } = room;
  const api = nativeApi();
  const [name, setName] = useState(() => localStorage.getItem('xennex_display_name') || '');
  const [code, setCode] = useState(initialRoom);
  const [publicUrl, setPublicUrl] = useState(() => localStorage.getItem('xennex_cloudflare_url') || 'https://xennex-live.alexdoong11.workers.dev');
  const [viewOnly, setViewOnly] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [fallbackPending, setFallbackPending] = useState(false);
  const closeCapture = useCallback(() => setCaptureOpen(false), []);
  const [peopleOpen, setPeopleOpen] = useState(true);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [readings, setReadings] = useState<Record<string, VideoReading>>({});
  const [notice, setNotice] = useState('');
  const [audible, setAudible] = useState<string[]>([]);
  const [focus, setFocus] = useState('');
  const [recent, setRecent] = useState<string[]>(() => {
    try { const items: unknown = JSON.parse(localStorage.getItem('xennex_room_history_v2') || '[]'); return Array.isArray(items) ? items.filter((x): x is string => typeof x === 'string' && !!normalizeRoom(x)).slice(0, 5) : []; }
    catch { return []; }
  });

  const connected = state.phase === 'connected';
  const inRoom = connected || state.phase === 'reconnecting';
  const busy = state.phase === 'connecting' || fallbackPending;
  const copy = async (value: string) => {
    try { await navigator.clipboard.writeText(value); setNotice('Copiado para a área de transferência.'); }
    catch { setNotice(`Copie manualmente: ${value}`); }
  };
  const publicLink = () => roomLink(api ? publicUrl : window.location.href, state.room);
  const invite = async () => {
    try {
      const link = publicLink();
      if (api) {
        const response = await fetch(new URL('xennex-stream.json', link), { signal: AbortSignal.timeout(5000), cache: 'no-store' });
        const version: unknown = response.ok ? await response.json() : null;
        if (!version || typeof version !== 'object' || !('protocol' in version) || version.protocol !== PROTOCOL) {
          setNotice('A página pública precisa ser atualizada. Publique cloudflare_pages/dist antes de convidar pelo navegador.'); return;
        }
      }
      await copy(link);
    } catch { setNotice('Não foi possível verificar a página pública. Confira o endereço Cloudflare e publique o build web atualizado.'); }
  };
  const enter = (host: boolean) => {
    setNotice(''); setFocus(''); setAudible([]); setViewOnly(false); setPeopleOpen(true); setCaptureOpen(false);
    const target = host && !code.trim() ? newRoomCode() : normalizeRoom(code);
    if (!target) { setNotice('Digite um código válido ou cole um link de convite.'); return; }
    setCode(target); localStorage.setItem('xennex_display_name', displayName(name));
    try { client.start(target, name, host); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Falha ao conectar.'); }
  };
  useEffect(() => {
    if (!state.room || state.phase !== 'connected') return;
    setRecent(current => {
      const next = [state.room, ...current.filter(id => id !== state.room)].slice(0, 5);
      localStorage.setItem('xennex_room_history_v2', JSON.stringify(next)); return next;
    });
  }, [state.room, state.phase]);
  useEffect(() => {
    const active = (event: BeforeUnloadEvent) => { if (client.getSnapshot().phase === 'connected') event.preventDefault(); };
    window.addEventListener('beforeunload', active); return () => window.removeEventListener('beforeunload', active);
  }, [client]);
  const publications = state.participants.flatMap(p => p.publications.map(publication => ({ ...publication, peerId: p.peerId, name: p.name })));
  const tiles = [...state.streams.entries()].map(([id, stream]) => {
    const publication = publications.find(p => p.id === id);
    return { id, stream, name: `${publication?.name || 'Participante'} · ${publication?.title || 'Transmissão'}`, local: false, quality: undefined as Quality | undefined };
  });
  for (const local of room.locals) tiles.unshift({ id: local.id, stream: local.stream, name: `${name || 'Você'} · ${local.title}`, local: true, quality: local.quality });
  const pending = publications.filter(p => state.watching.includes(p.id) && !state.streams.has(p.id));
  const newPublicationIds = new Set(room.newScreens.map(s => s.publicationId));
  const newSharers = new Set(room.newScreens.map(s => s.peerId));
  const validFocus = tiles.some(tile => tile.id === focus) ? focus : '';
  const statusLabel = { idle: 'Pronto para conectar', connecting: 'Conectando', connected: 'Na sala', reconnecting: 'Reconectando', error: 'Falha na conexão', closed: 'Sala encerrada' }[state.phase];
  return <section className={`stream-workspace ${standalone ? 'stream-standalone' : ''} ${viewOnly && inRoom ? 'room-view-only' : ''} ${inRoom ? 'room-active' : ''} ${peopleOpen ? 'room-show-people' : ''} ${diagnosticsOpen ? 'room-show-diagnostics' : ''}`}>
    <header className="room-header"><div className="room-brand"><span className="room-brand-icon"><Radio size={24}/></span><div><h1>Xennex Live</h1><p>Sua sala. Suas telas. Todo mundo junto.</p></div></div>
      <span className={`room-status room-status-${state.phase}`}><i/>{statusLabel}</span></header>
    {(notice || state.message || room.captureError || room.warning) && <div className="room-notice" role="status">{[notice, state.message, room.captureError, room.warning].filter(Boolean).join(' · ')}</div>}
    {!inRoom && <RoomEntryDiagnostic entry={state.entry} phase={state.phase} alternative={state.transport === 'alternative' || HAS_TURN}/>}
    <TurnFallbackPanel client={client} state={state} code={code} name={name} base={api ? publicUrl : window.location.href} onPending={setFallbackPending}/>
    {!inRoom && <div className="room-lobby">
      <div className="room-welcome"><span className="room-eyebrow">COMPARTILHE O MOMENTO</span><h2>O próximo encontro<br/>começa por uma tela.</h2><p>Crie uma sala ou entre com um convite. Assista e compartilhe pelo aplicativo ou pelo navegador.</p><div className="room-feature-list"><span><Monitor size={18}/>Várias transmissões</span><span><Users size={18}/>Até {MAX_PARTICIPANTS} pessoas</span><span><Link size={18}/>Um link para entrar</span></div></div>
      <form className="room-entry" onSubmit={event => { event.preventDefault(); enter(false); }}>
        <h3>Vamos nos conectar</h3><label>Seu nome<input maxLength={40} value={name} onChange={event => setName(event.target.value)} placeholder="Como você quer aparecer?" disabled={busy}/></label>
        <label>Código ou link da sala<input value={code} onChange={event => setCode(event.target.value)} placeholder="XNX-… ou link do convite" disabled={busy}/></label>
        <button className="room-primary" type="submit" disabled={busy || !code.trim()}><LogIn size={18}/>Entrar na sala</button>
        <button type="button" onClick={() => enter(true)} disabled={busy}><Plus size={18}/>Criar sala {code.trim() ? 'com este código' : 'com novo código'}</button>
        {busy && <button type="button" onClick={() => client.leave()}>Cancelar conexão</button>}
        <small>Primeiro participante? Use “Criar sala”. Os demais usam “Entrar”. A sala continua enquanto houver alguém.</small>
        {recent.length > 0 && <div className="room-recent"><span>Recentes</span>{recent.map(id => <button type="button" key={id} onClick={() => setCode(id)}>{id}</button>)}</div>}
      </form>
    </div>}
    {inRoom && <>
      <div className="room-toolbar"><div><small>{state.isHost ? 'COORDENANDO A SALA' : 'SALA CONECTADA'}</small><strong>{state.room}</strong></div>
        <button title="Copiar código" onClick={() => void copy(state.room)}><Copy size={16}/>Código</button>
        <button onClick={() => void invite()}><Link size={16}/>Convidar</button>
        {api && <button onClick={() => void api.OpenStreamViewer(state.room, 'Xennex Live')}><ExternalLink size={16}/>Janela separada</button>}
        <button aria-pressed={viewOnly} onClick={() => { setPeopleOpen(viewOnly); setViewOnly(value => !value); }}><Monitor size={16}/>{viewOnly ? 'Voltar aos controles' : 'Somente telas'}</button>
        <span className="room-spacer"/>
        <button className="room-primary" aria-haspopup="dialog" onClick={() => setCaptureOpen(true)}><ScreenShare size={16}/>{room.locals.length ? `Transmitindo · ${room.locals.length}` : 'Transmitir'}</button>
        <button className={room.newScreens.length ? 'room-new-live-button' : undefined} aria-label="Pessoas e telas" aria-description={room.newScreens.length ? `${room.newScreens.length} novas transmissões disponíveis` : undefined} aria-pressed={peopleOpen} onClick={() => setPeopleOpen(value => !value)}><Users size={16}/>Pessoas e telas{room.newScreens.length > 0 && <span className="room-new-live-badge" aria-hidden="true">{room.newScreens.length}</span>}</button>
        <button aria-pressed={diagnosticsOpen} onClick={() => setDiagnosticsOpen(value => !value)}><Activity size={16}/>Qualidade</button>
        <button aria-expanded={toolsOpen} onClick={() => setToolsOpen(value => !value)}>Conversa e notas</button>
        <button className="room-danger" onClick={() => void room.leave()}><LogOut size={16}/>Sair</button>
      </div>
      {room.capturing && !captureOpen && <CaptureProgress phase={room.capturePhase} cancel={room.cancel}/>}
      <StreamCapturePanel open={captureOpen} onClose={closeCapture}/>
      <div hidden={!toolsOpen}><RoomToolsPanel key={client.sessionId} view={state.workspace} client={client.workspace}/></div>
      <div className="room-body"><main className="room-stage">
        <StreamStage tiles={tiles} readings={readings} audible={audible} focus={validFocus} onFocus={setFocus}
          onAudio={id => setAudible(ids => ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id])}/>
        {pending.length > 0 && <div className="room-notice" role="status">Conectando ao vídeo de {pending.map(p => `${p.name}: ${p.title}`).join(', ')}… Se continuar aguardando, confira a conexão e a configuração TURN. <button onClick={() => client.retryWatching()}>Tentar vídeo novamente</button></div>}
        <RoomDiagnostics client={client} onReadings={setReadings}/>
        {diagnosticsOpen && <CapturePipelineDiagnostics captures={room.locals}/>}

      </main><aside className="room-people"><h3><Users size={18}/>Pessoas <span>{state.participants.length}/{MAX_PARTICIPANTS}</span></h3>
        {state.participants.map(p => <div key={p.peerId} className="room-person-group"><div className="room-person"><span className="room-avatar">{p.name.slice(0, 1).toUpperCase()}</span><div><strong className={newSharers.has(p.peerId) ? 'room-new-live-name' : undefined}>{p.name}{p.peerId === state.selfId ? ' (você)' : ''}</strong><small>{p.peerId === state.coordinator ? 'Coordenador · ' : ''}{p.publications.length} transmissões</small></div></div>
          {p.publications.map(publication => <div className="room-publication" key={publication.id}><span>{publication.kind === 'camera' ? 'Câmera' : 'Tela'} · {publication.title}</span>{p.peerId !== state.selfId && <button className={newPublicationIds.has(publication.id) ? 'room-new-live-button' : undefined} aria-pressed={state.watching.includes(publication.id)} title={state.watching.includes(publication.id) ? 'Parar de assistir' : newPublicationIds.has(publication.id) ? 'Nova transmissão disponível' : 'Assistir'} aria-label={`${state.watching.includes(publication.id) ? 'Parar de assistir' : 'Assistir'} ${p.name}: ${publication.title}`} disabled={!state.watching.includes(publication.id) && state.watching.length >= MAX_WATCHING} onClick={() => client.setWatching(state.watching.includes(publication.id) ? state.watching.filter(id => id !== publication.id) : [...state.watching, publication.id])}>{state.watching.includes(publication.id) ? <><Square size={14}/>Parar</> : <><Monitor size={14}/>Assistir{newPublicationIds.has(publication.id) && <span className="room-new-live-badge" aria-hidden="true">Nova</span>}</>}</button>}</div>)}
        </div>)}
        <p className="room-helper">Escolha até {MAX_WATCHING} transmissões. Ative e ajuste o áudio de cada uma independentemente, inclusive com outra tela em destaque.</p>
        <label>Alterar seu nome<input value={name} maxLength={40} onChange={event => setName(event.target.value)} onBlur={() => { client.setName(name); localStorage.setItem('xennex_display_name', displayName(name)); }}/></label>
      </aside></div>
    </>}
    <details className="room-options"><summary>Opções da conexão</summary><div>
      {api && <label>Endereço público do seu Cloudflare<input value={publicUrl} onChange={event => setPublicUrl(event.target.value)} onBlur={() => localStorage.setItem('xennex_cloudflare_url', publicUrl)}/></label>}
      <p>{HAS_TURN ? 'Servidor de retransmissão configurado; sua disponibilidade depende do servidor e das credenciais.' : 'Sem retransmissão TURN configurada. Redes restritas podem impedir a entrada na sala ou a chegada dos vídeos, mesmo quando a página abre normalmente.'}</p>
      <small>Salas: geração 3. App e página web devem usar esta mesma geração; salas das versões anteriores não são compatíveis. A hospedagem Cloudflare entrega a página; não retransmite o vídeo automaticamente.</small>
      {state.entry && <button onClick={() => void copy(entryReport(state.entry!, state.phase, state.transport === 'alternative' || HAS_TURN))}><Copy size={16}/>Copiar diagnóstico</button>}
      {state.diagnostics.length > 0 && <>
        <details><summary>Diagnóstico da conexão</summary><pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{state.diagnostics.join('\n')}</pre></details></>}
    </div></details>
  </section>;
}
