import { useEffect, useState } from 'react';
import { Radio, Link, Copy, LogIn, Plus, ScreenShare, Square, Users, RefreshCw, LogOut, Monitor, ExternalLink } from 'lucide-react';
import { useRoom } from './useRoom';
import { nativeApi, type AudioProcess, type CaptureOptions } from './capture';
import { DEFAULT_QUALITY, QUALITY_PRESETS, type Quality, type Resolution } from './quality';
import { displayName, PROTOCOL, MAX_PARTICIPANTS, MAX_LOCAL_STREAMS, MAX_WATCHING, newRoomCode, normalizeRoom, roomLink } from './protocol';
import { HAS_TURN } from './peerConfig';
import StreamVideo from './StreamVideo';
import RoomDiagnostics from './RoomDiagnostics';
import './stream-workspace.css';

export default function StreamWorkspace({ initialRoom = '', standalone = false }: { initialRoom?: string; standalone?: boolean }) {
  const room = useRoom(); const { state, client } = room;
  const api = nativeApi();
  const [name, setName] = useState(() => localStorage.getItem('xennex_display_name') || '');
  const [code, setCode] = useState(initialRoom);
  const [title, setTitle] = useState('Minha transmissão');
  const [publicUrl, setPublicUrl] = useState(() => localStorage.getItem('xennex_cloudflare_url') || 'https://xennex-live.alexdoong11.workers.dev');
  const [quality, setQuality] = useState<Quality>(DEFAULT_QUALITY);
  const [source, setSource] = useState<CaptureOptions['source']>(api ? 'window' : 'browser');
  const [audio, setAudio] = useState<CaptureOptions['audio']>(api ? 'process' : 'system');
  const [processes, setProcesses] = useState<AudioProcess[]>([]);
  const [processId, setProcessId] = useState('');
  const [loadingProcesses, setLoadingProcesses] = useState(false);
  const [notice, setNotice] = useState('');
  const [audible, setAudible] = useState<string[]>([]);
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [cameraId, setCameraId] = useState('');
  const [focus, setFocus] = useState('');
  const [recent, setRecent] = useState<string[]>(() => {
    try { const items: unknown = JSON.parse(localStorage.getItem('xennex_room_history_v2') || '[]'); return Array.isArray(items) ? items.filter((x): x is string => typeof x === 'string' && !!normalizeRoom(x)).slice(0, 5) : []; }
    catch { return []; }
  });

  const connected = state.phase === 'connected';
  const inRoom = connected || state.phase === 'reconnecting';
  const busy = state.phase === 'connecting';
  const selectedProcess = processes.find(p => String(p.Hwnd) === processId);
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
    setNotice(''); setFocus(''); setAudible([]);
    const target = host && !code.trim() ? newRoomCode() : normalizeRoom(code);
    if (!target) { setNotice('Digite um código válido ou cole um link de convite.'); return; }
    setCode(target); localStorage.setItem('xennex_display_name', displayName(name));
    try { client.start(target, name, host); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Falha ao conectar.'); }
  };
  const refreshProcesses = async () => {
    if (!api) return;
    setLoadingProcesses(true);
    try {
      const parsed: AudioProcess[] = JSON.parse(await api.GetAudioProcesses());
      setProcesses(parsed.filter(p => p.Hwnd > 0));
    } catch { setNotice('Não foi possível listar as janelas. Tente novamente.'); }
    finally { setLoadingProcesses(false); }
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
    return { id, stream, name: `${publication?.name || 'Participante'} · ${publication?.title || 'Transmissão'}`, local: false };
  });
  for (const local of room.locals) tiles.unshift({ id: local.id, stream: local.stream, name: `${name || 'Você'} · ${local.title}`, local: true });
  const pending = publications.filter(p => state.watching.includes(p.id) && !state.streams.has(p.id));
  const nativeBusy = room.locals.some(local => local.source === 'window' || local.source === 'monitor');
  const validFocus = tiles.some(tile => tile.id === focus) ? focus : '';
  const statusLabel = { idle: 'Pronto para conectar', connecting: 'Conectando', connected: 'Na sala', reconnecting: 'Reconectando', error: 'Falha na conexão', closed: 'Sala encerrada' }[state.phase];
  const refreshCameras = async () => {
    try { setCameras((await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput')); }
    catch { setNotice('Não foi possível listar as câmeras. Use a câmera padrão ou confira a permissão.'); }
  };
  const setSourceMode = (value: CaptureOptions['source']) => {
    setSource(value);
    if (value === 'camera') { setAudio('none'); void refreshCameras(); }
    else if (value === 'browser') setAudio('system');
    else { setAudio('process'); void refreshProcesses(); }
  };
  return <section className={`stream-workspace ${standalone ? 'stream-standalone' : ''}`}>
    <header className="room-header"><div className="room-brand"><span className="room-brand-icon"><Radio size={24}/></span><div><h1>Xennex Live</h1><p>Sua sala. Suas telas. Todo mundo junto.</p></div></div>
      <span className={`room-status room-status-${state.phase}`}><i/>{statusLabel}</span></header>
    {(notice || state.message || room.captureError || room.warning) && <div className="room-notice" role="status">{[notice, state.message, room.captureError, room.warning].filter(Boolean).join(' · ')}</div>}
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
        {api && <button onClick={() => void api.OpenStreamViewer(state.room, title)}><ExternalLink size={16}/>Janela separada</button>}
        <span className="room-spacer"/><button className="room-danger" onClick={() => void room.leave()}><LogOut size={16}/>Sair</button>
      </div>
      <div className="room-body"><main className="room-stage">
        <div className={`room-grid ${validFocus ? 'room-grid-focus' : ''}`}>
          {tiles.map(tile => <div key={tile.id} inert={!!validFocus && tile.id !== validFocus} aria-hidden={!!validFocus && tile.id !== validFocus} className={validFocus && tile.id !== validFocus ? 'room-background-media' : 'room-tile'}><StreamVideo {...tile} audible={audible.includes(tile.id)} focused={tile.id === validFocus}
            onAudio={() => setAudible(ids => ids.includes(tile.id) ? ids.filter(id => id !== tile.id) : [...ids, tile.id])} onFocus={() => setFocus(validFocus === tile.id ? '' : tile.id)}/></div>)}
          {!tiles.length && <div className="room-empty"><ScreenShare size={40}/><h3>A sala está pronta</h3><p>Compartilhe sua tela ou aguarde alguém começar.</p><small>O áudio de cada transmissão é ativado por você.</small></div>}
        </div>
        {pending.length > 0 && <div className="room-notice" role="status">Conectando ao vídeo de {pending.map(p => `${p.name}: ${p.title}`).join(', ')}… Se continuar aguardando, confira a conexão e a configuração TURN. <button onClick={() => client.retryWatching()}>Tentar vídeo novamente</button></div>}
        <RoomDiagnostics client={client}/>
        <details className="room-capture" open><summary><ScreenShare size={18}/>Adicionar transmissão · {room.locals.length}/{MAX_LOCAL_STREAMS}</summary>
          <div className="room-capture-form"><label>Título<input value={title} maxLength={80} disabled={room.capturing} onChange={event => setTitle(event.target.value)}/></label>
            <label>Capturar<select value={source} disabled={room.capturing} onChange={event => setSourceMode(event.target.value as CaptureOptions['source'])}><option value="browser">Selecionar tela / janela / aba</option><option value="camera">Câmera</option>{api && <><option value="window" disabled={nativeBusy}>Janela do Windows</option><option value="monitor" disabled={nativeBusy}>Monitor principal do Windows</option></>}</select></label>
            {(source === 'window' || source === 'monitor') && <label>Janela / processo<div className="room-input-action"><select value={processId} disabled={room.capturing} onFocus={() => { if (!processes.length) void refreshProcesses(); }} onChange={event => setProcessId(event.target.value)}><option value="">Selecione uma janela</option>{processes.map(p => <option key={p.Hwnd} value={p.Hwnd}>{p.Title} — {p.Name}</option>)}</select><button title="Atualizar janelas" onClick={() => void refreshProcesses()} disabled={loadingProcesses}><RefreshCw size={16}/></button></div></label>}
            {source === 'camera' && <label>Câmera<select value={cameraId} onFocus={() => void refreshCameras()} onChange={event => setCameraId(event.target.value)}><option value="">Câmera padrão</option>{cameras.map((camera, index) => <option key={camera.deviceId || index} value={camera.deviceId}>{camera.label || `Câmera ${index + 1}`}</option>)}</select></label>}
            <label>Áudio<select value={audio} disabled={room.capturing} onChange={event => setAudio(event.target.value as CaptureOptions['audio'])}><option value="none">Sem áudio</option>{source === 'camera' ? <option value="microphone">Microfone</option> : <option value="system">{source === 'browser' ? 'Áudio oferecido pelo navegador' : 'Áudio do sistema'}</option>}{api && (source === 'window' || source === 'monitor') && <option value="process">Somente o processo selecionado</option>}</select></label>
            <label>Resolução máxima<select value={quality.resolution} disabled={room.capturing} onChange={event => setQuality({ ...quality, resolution: event.target.value as Resolution })}>{Object.entries(QUALITY_PRESETS).map(([key, preset]) => <option key={key} value={key}>{preset.label}</option>)}</select></label>
            <label>Limite de FPS (0 = automático)<input type="number" min={0} max={120} step={1} value={quality.fps} disabled={room.capturing} onChange={event => setQuality({ ...quality, fps: Math.max(0, Math.min(120, Math.round(Number(event.target.value) || 0))) })}/></label>
            <label>Prioridade<select value={quality.preference} disabled={room.capturing} onChange={event => setQuality({ ...quality, preference: event.target.value as Quality['preference'] })}><option value="motion">Fluidez (jogos)</option><option value="detail">Nitidez (texto)</option></select></label>
            <label>Upload disponível (Mbps)<input type="number" min={1} max={100} value={quality.uploadMbps} disabled={room.capturing} onChange={event => setQuality({ ...quality, uploadMbps: Math.max(1, Math.min(100, Number(event.target.value) || 1)) })}/></label>
          </div>
          <div className="room-share-action"><p>{source === 'browser' ? 'Escolha a fonte no seletor e marque compartilhar áudio, quando disponível.' : 'A captura é local. Somente as pessoas que assistem recebem a transmissão.'}<br/><small>A resolução preserva a proporção original. A qualidade se adapta à conexão e ao número de espectadores.</small></p>
            {room.capturing ? <button className="room-danger" onClick={room.cancel}><Square size={17}/>Cancelar</button> : <button className="room-primary" disabled={!connected || room.locals.length >= MAX_LOCAL_STREAMS || (nativeBusy && (source === 'window' || source === 'monitor'))} onClick={() => void room.share({ source, audio, cameraId, process: selectedProcess, quality }, title)}><ScreenShare size={18}/>{source === 'camera' ? 'Adicionar câmera' : 'Compartilhar tela'}</button>}

          </div>
          {nativeBusy && <p className="room-helper">Uma captura nativa ativa. Para adicionar outra tela, use “Selecionar tela / janela / aba”.</p>}
          {room.locals.map(local => <div className="room-local-source" key={local.id}><span>{local.title} · {local.kind === 'camera' ? 'Câmera' : 'Tela'} · {local.quality.fps || 'Auto'} FPS</span><button className="room-danger" onClick={() => void room.stop(local.id)} aria-label={`Parar ${local.title}`}><Square size={14}/>Parar</button></div>)}
        </details>
      </main><aside className="room-people"><h3><Users size={18}/>Pessoas <span>{state.participants.length}/{MAX_PARTICIPANTS}</span></h3>
        {state.participants.map(p => <div key={p.peerId} className="room-person-group"><div className="room-person"><span className="room-avatar">{p.name.slice(0, 1).toUpperCase()}</span><div><strong>{p.name}{p.peerId === state.selfId ? ' (você)' : ''}</strong><small>{p.peerId === state.coordinator ? 'Coordenador · ' : ''}{p.publications.length} transmissões</small></div></div>
          {p.publications.map(publication => <div className="room-publication" key={publication.id}><span>{publication.kind === 'camera' ? 'Câmera' : 'Tela'} · {publication.title}</span>{p.peerId !== state.selfId && <button title={state.watching.includes(publication.id) ? 'Parar de assistir' : 'Assistir'} aria-label={`${state.watching.includes(publication.id) ? 'Parar de assistir' : 'Assistir'} ${p.name}: ${publication.title}`} disabled={!state.watching.includes(publication.id) && state.watching.length >= MAX_WATCHING} onClick={() => client.setWatching(state.watching.includes(publication.id) ? state.watching.filter(id => id !== publication.id) : [...state.watching, publication.id])}>{state.watching.includes(publication.id) ? <Square size={14}/> : <Monitor size={14}/>}</button>}</div>)}
        </div>)}
        <p className="room-helper">Escolha até {MAX_WATCHING} transmissões. Ative e ajuste o áudio de cada uma independentemente, inclusive com outra tela em destaque.</p>
        <label>Alterar seu nome<input value={name} maxLength={40} onChange={event => setName(event.target.value)} onBlur={() => { client.setName(name); localStorage.setItem('xennex_display_name', displayName(name)); }}/></label>
      </aside></div>
    </>}
    <details className="room-options"><summary>Opções da conexão</summary><div>
      {api && <label>Endereço público do seu Cloudflare<input value={publicUrl} onChange={event => setPublicUrl(event.target.value)} onBlur={() => localStorage.setItem('xennex_cloudflare_url', publicUrl)}/></label>}
      <p>{HAS_TURN ? 'Servidor de retransmissão configurado para redes que não permitem conexão direta.' : 'Conexão direta entre participantes. Se a sala conectar mas o vídeo não chegar entre redes diferentes, será necessário configurar um servidor TURN.'}</p>
      <small>Salas: geração 3. App e página web devem usar esta mesma geração; salas das versões anteriores não são compatíveis. A hospedagem Cloudflare entrega a página; não retransmite o vídeo automaticamente.</small>
      {state.diagnostics.length > 0 && <details><summary>Diagnóstico da conexão</summary><pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{state.diagnostics.join('\n')}</pre></details>}
    </div></details>
  </section>;
}
