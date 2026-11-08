import { useEffect, useRef, useState } from 'react';
import { ScreenShare, Square, RefreshCw, X, Monitor, Camera, AppWindow } from 'lucide-react';
import { useStreamContext } from './StreamContext';
import CaptureProgress from './CaptureProgress';
import StreamCompatibilityOptions from './StreamCompatibilityOptions';
import { captureSupport } from './streamCapabilities';
import { browserCaptureStatus, browserCaptureReport, screenCaptureExplanation } from './browserCaptureSupport';
import { nativeApi, type AudioProcess, type CaptureOptions, type CaptureMonitor } from './capture';
import { DEFAULT_QUALITY, QUALITY_PRESETS, type Quality, type Resolution } from './quality';
import { MAX_LOCAL_STREAMS } from './protocol';

export default function StreamCapturePanel({ open, onClose }: { open: boolean; onClose(): void }) {
  const room = useStreamContext();
  const api = nativeApi();
  const support = captureSupport();
  const browserSupport = browserCaptureStatus();
  const connected = room.state.phase === 'connected';
  const [notice, setNotice] = useState('');
  const [title, setTitle] = useState('Minha transmissão');
  const [quality, setQuality] = useState<Quality>(DEFAULT_QUALITY);
  const [source, setSource] = useState<CaptureOptions['source']>('browser');
  const [audio, setAudio] = useState<CaptureOptions['audio']>(api ? 'process' : 'system');
  const [processes, setProcesses] = useState<AudioProcess[]>([]);
  const [processId, setProcessId] = useState('');
  const [audioProcessId, setAudioProcessId] = useState('');
  const [loadingProcesses, setLoadingProcesses] = useState(false);
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [cameraId, setCameraId] = useState('');
  const [monitors, setMonitors] = useState<CaptureMonitor[]>([]);
  const [monitorId, setMonitorId] = useState('');
  const [monitorBackend, setMonitorBackend] = useState<'dxgi' | 'wgc'>('dxgi');
  const [loadingMonitors, setLoadingMonitors] = useState(false);
  const windows = processes.filter((p, i, all) => p.Hwnd > 0 && all.findIndex(other => other.Hwnd === p.Hwnd) === i);
  const audioProcesses = processes.filter((p, i, all) => p.Pid > 0 && all.findIndex(other => other.Pid === p.Pid) === i);
  const selectedAudioProcess = audioProcesses.find(p => String(p.Pid) === audioProcessId);
  const selectedProcess = processes.find(p => String(p.Hwnd) === processId);
  const refreshProcesses = async () => {
    if (!api) return;
    setLoadingProcesses(true);
    try {
      const parsed: AudioProcess[] = JSON.parse(await api.GetAudioProcesses());
      setProcesses(parsed);
    } catch { setNotice('Não foi possível listar as janelas. Tente novamente.'); }
    finally { setLoadingProcesses(false); }
  };
  const refreshCameras = async () => {
    try { setCameras((await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput')); }
    catch { setNotice('Não foi possível listar as câmeras. Use a câmera padrão ou confira a permissão.'); }
  };
  const refreshMonitors = async () => {
    if (!api) return;
    setLoadingMonitors(true);
    try {
      const available: CaptureMonitor[] = JSON.parse(await api.GetCaptureMonitors());
      setMonitors(available);
      setMonitorId(current => current || available.find(monitor => monitor.Primary)?.Id || available[0]?.Id || '');
    } catch { setNotice('Não foi possível listar os monitores. Atualize o aplicativo e tente novamente.'); }
    finally { setLoadingMonitors(false); }
  };
  const setSourceMode = (value: CaptureOptions['source']) => {
    setSource(value);
    if (value === 'camera') { setAudio('none'); void refreshCameras(); }
    else if (value === 'browser') { setAudio(api && !nativeBusy ? 'process' : 'system'); if (api) void refreshProcesses(); }
    else { setAudio(value === 'monitor' ? 'system' : 'process'); void refreshProcesses(); if (value === 'monitor') void refreshMonitors(); }
  };
  const share = () => {
    if ((source === 'browser' && !support.screen) || (source === 'camera' && !support.camera)) {
      setNotice('Esta fonte não está disponível neste navegador. Você ainda pode assistir às transmissões da sala.'); return;
    }
    if (source === 'monitor' && monitorBackend === 'dxgi' && !monitors.some(monitor => monitor.Id === monitorId)) {
      setNotice('Selecione um monitor disponível. Não vamos trocar automaticamente para outra tela.'); return;
    }
    if (audio === 'process' && audioProcessId && !selectedAudioProcess) {
      setNotice('A fonte de áudio escolhida não está mais disponível. Atualize e selecione novamente.'); return;
    }
    void room.share({ source, audio, cameraId, monitorId, monitorBackend, process: selectedProcess, audioProcess: selectedAudioProcess, quality }, title);
  };
  const nativeBusy = room.locals.some(local => local.nativeSession || local.source === 'window' || local.source === 'monitor' || local.source === 'game');
  const dialog = useRef<HTMLDialogElement>(null);
  const previousCount = useRef(room.locals.length);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open && dialog.current?.open) dialog.current.close();
  }, [open]);
  useEffect(() => {
    if (room.locals.length > previousCount.current) onClose();
    previousCount.current = room.locals.length;
  }, [room.locals.length, onClose]);
  const choices: { value: CaptureOptions['source']; label: string; icon: typeof Monitor }[] = [
    { value: 'browser', label: 'Tela, janela ou aba', icon: Monitor },
    { value: 'camera', label: 'Câmera', icon: Camera },
    ...(api ? [{ value: 'window' as const, label: 'Janela com áudio de processo', icon: AppWindow }, { value: 'monitor' as const, label: 'Monitor inteiro', icon: Monitor }] : []),
    ...(api ? [{ value: 'game' as const, label: 'Jogo OpenGL · experimental', icon: AppWindow }] : []),
  ];
  return <dialog ref={dialog} className="room-capture-dialog" aria-label="Compartilhar uma transmissão" onCancel={onClose} onClose={onClose}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="room-capture-content">
      <header className="room-panel-heading"><div><span className="room-eyebrow">VAMOS COMPARTILHAR</span><h2>O que vamos assistir?</h2></div>
        <button aria-label="Fechar painel de transmissão" onClick={onClose}><X size={18}/></button></header>
      <p className="room-helper">Escolha a fonte e a qualidade. A seleção da tela é confirmada por você antes de começar.</p>
      <div className="room-source-choices">{choices.map(choice => <button key={choice.value} aria-pressed={source === choice.value}
        disabled={room.capturing || (choice.value === 'browser' && !support.screen) || (choice.value === 'camera' && !support.camera) || (nativeBusy && (choice.value === 'window' || choice.value === 'monitor' || choice.value === 'game'))}
        onClick={() => setSourceMode(choice.value)}><choice.icon size={22}/>{choice.label}</button>)}</div>
      {nativeBusy && <p className="room-notice" role="status">O vídeo nativo ou áudio por processo já está em uso. Para adicionar outra tela, escolha <button type="button" disabled={room.capturing} onClick={() => setSourceMode('browser')}>Tela, janela ou aba</button> com áudio do navegador, ou pare a captura atual na lista abaixo.</p>}
      {api && source === 'browser' && <p className="room-helper">Vídeo otimizado para transmitir. Você escolhe a tela no seletor e pode combinar com o som de um programa específico abaixo.</p>}
      {!support.screen && support.watch && <p className="room-helper" role="status">Este navegador não oferece captura de tela. Você pode assistir às transmissões{support.camera ? ' e compartilhar sua câmera' : ''}.</p>}
      {browserSupport.screen !== 'available' && <p className="room-notice" role="status">{screenCaptureExplanation(browserSupport)}</p>}
      {browserSupport.screen === 'missing-api' && connected && !api && <p className="room-help">
        <a className="btn" href={`xennex-live://share?room=${encodeURIComponent(room.state.room)}`}>Abrir capturador Android</a>
        {' '}Requer o APK de prévia instalado. O app pedirá sua confirmação antes de capturar.
      </p>}
      <details className="room-capture-environment"><summary>Diagnóstico de captura deste aparelho</summary>
        <p className="room-helper">Copie estes dados se precisar relatar um problema. Eles não incluem imagem, nome, sala ou endereço de rede.</p>
        <textarea aria-label="Diagnóstico de captura" readOnly rows={7} value={browserCaptureReport(browserSupport)}/>
      </details>
      {source === 'window' && <p className="room-helper">Para osu! em fullscreen, experimente “Jogo OpenGL”. A captura de janela não muda para o monitor inteiro sozinha.</p>}
      {source === 'game' && <p className="room-notice">Captura direta de jogos OpenGL, como osu!, sem OBS. Escolha a janela e volte ao jogo após iniciar. Este modo carrega um módulo do Xennex no jogo e pode afetar sua compatibilidade; ele não contorna proteções. Reiniciar o jogo remove o módulo.</p>}
          {source === 'monitor' && <p className="room-notice">Este modo compartilha todo o monitor escolhido, inclusive o desktop ao dar Alt+Tab. DXGI recupera trocas de modo, mas o Windows pode bloquear o fluxo de jogos como osu! em tela cheia exclusiva. Se a imagem congelar ou a captura reiniciar repetidamente, teste o jogo em janela/sem bordas.</p>}
      {(notice || room.captureError) && <p className="room-notice" role="status">{notice || room.captureError}</p>}
        <div className="room-capture"><h3><ScreenShare size={18}/>Adicionar transmissão · {room.locals.length}/{MAX_LOCAL_STREAMS}</h3>
          {room.capturing && <CaptureProgress phase={room.capturePhase} cancel={room.cancel}/>}
          <div className="room-capture-form"><label>Título<input value={title} maxLength={80} disabled={room.capturing} onChange={event => setTitle(event.target.value)}/></label>
            {source === 'monitor' && <><label>Método de captura<select aria-label="Método de captura" value={monitorBackend} disabled={room.capturing} onChange={event => setMonitorBackend(event.target.value as 'dxgi' | 'wgc')}><option value="dxgi">DXGI · compatível com fullscreen exclusivo</option><option value="wgc">WGC · monitor principal</option></select></label>
            {monitorBackend === 'dxgi' && <label>Monitor do jogo<div className="room-input-action"><select aria-label="Monitor do jogo" value={monitorId} disabled={room.capturing || loadingMonitors} onChange={event => setMonitorId(event.target.value)}><option value="">Selecione um monitor</option>{monitors.map((monitor, index) => <option key={monitor.Id} value={monitor.Id}>Monitor {index + 1}{monitor.Primary ? ' · principal' : ''} · {monitor.Width} × {monitor.Height}</option>)}</select><button title="Atualizar monitores" disabled={room.capturing || loadingMonitors} onClick={() => void refreshMonitors()}><RefreshCw size={16}/></button></div></label>}</>}

            {(source === 'window' || source === 'game') && <label>{source === 'game' ? 'Janela do jogo OpenGL' : 'Janela do vídeo'}<div className="room-input-action"><select value={processId} disabled={room.capturing} onFocus={() => { if (!processes.length) void refreshProcesses(); }} onChange={event => setProcessId(event.target.value)}><option value="">Selecione uma janela</option>{windows.map(p => <option key={p.Hwnd} value={p.Hwnd}>{p.Title} — {p.Name}</option>)}</select><button title="Atualizar janelas" onClick={() => void refreshProcesses()} disabled={loadingProcesses}><RefreshCw size={16}/></button></div></label>}
            {source === 'camera' && <label>Câmera<select value={cameraId} onFocus={() => void refreshCameras()} onChange={event => setCameraId(event.target.value)}><option value="">Câmera padrão</option>{cameras.map((camera, index) => <option key={camera.deviceId || index} value={camera.deviceId}>{camera.label || `Câmera ${index + 1}`}</option>)}</select></label>}
            <label>Áudio<select aria-label="Áudio" value={audio} disabled={room.capturing} onChange={event => setAudio(event.target.value as CaptureOptions['audio'])}><option value="none">Sem áudio</option>{source === 'camera' ? <option value="microphone">Microfone</option> : <option value="system">{source === 'browser' ? 'Áudio oferecido pelo navegador' : 'Áudio do sistema'}</option>}{api && source !== 'camera' && <option value="process" disabled={nativeBusy}>Escolher janela / processo de áudio</option>}</select></label>
            {source !== 'camera' && audio === 'process' && <label>Fonte independente de áudio<div className="room-input-action"><select value={audioProcessId} disabled={room.capturing} onFocus={() => { if (!processes.length) void refreshProcesses(); }} onChange={event => setAudioProcessId(event.target.value)}>
              <option value="">{source === 'window' || source === 'game' ? 'Mesma janela do vídeo' : 'Selecione o processo de áudio'}</option>
              {audioProcesses.map(p => <option key={p.Pid} value={p.Pid}>{p.Title || p.Name} — {p.Name} (PID {p.Pid}){p.HasActiveAudio ? ' · áudio ativo' : ''}</option>)}
            </select><button title="Atualizar fontes de áudio" onClick={() => void refreshProcesses()} disabled={loadingProcesses}><RefreshCw size={16}/></button></div><small>O som pertence ao processo e seus filhos. Janelas ou abas do mesmo processo podem compartilhar áudio.</small></label>}
            <label>Resolução alvo<select value={quality.resolution} disabled={room.capturing} onChange={event => setQuality({ ...quality, resolution: event.target.value as Resolution })}>{Object.entries(QUALITY_PRESETS).map(([key, preset]) => <option key={key} value={key}>{preset.label}</option>)}</select></label>
            <label>Limite de FPS (0 = automático)<input type="number" min={0} max={120} step={1} value={quality.fps} disabled={room.capturing} onChange={event => setQuality({ ...quality, fps: Math.max(0, Math.min(120, Math.round(Number(event.target.value) || 0))) })}/><span className="room-fps-presets">{[30, 60, 120, 0].map(fps => <button key={fps} type="button" disabled={room.capturing}
              aria-label={fps ? `Usar ${fps} FPS` : 'Usar FPS automático'} aria-pressed={quality.fps === fps} onClick={() => setQuality({ ...quality, fps })}>{fps || 'Auto'}</button>)}</span></label>

          </div>
          <details className="room-capture-advanced"><summary>Ajustes avançados de qualidade e conexão</summary><div className="room-capture-form">
            <StreamCompatibilityOptions quality={quality} onChange={setQuality} active={open} disabled={room.capturing}/>
            <label>Prioridade<select value={quality.preference} disabled={room.capturing} onChange={event => setQuality({ ...quality, preference: event.target.value as Quality['preference'] })}><option value="motion">Fluidez (jogos)</option><option value="detail">Nitidez (texto)</option></select></label>
            <label>Entrega da qualidade<select value={quality.delivery || 'preserve'} disabled={room.capturing} onChange={event => setQuality({ ...quality, delivery: event.target.value as Quality['delivery'] })}><option value="preserve">Preservar resolução escolhida</option><option value="adaptive">Adaptar à conexão</option></select></label>
            <label>Upload disponível (Mbps)<input type="number" min={1} max={1000} value={quality.uploadMbps} disabled={room.capturing} onChange={event => setQuality({ ...quality, uploadMbps: Math.max(1, Math.min(1000, Number(event.target.value) || 1)) })}/></label>
          </div></details>
          <div className="room-share-action"><details><summary>Sobre áudio e qualidade</summary><p>{source === 'browser' ? 'Escolha a fonte no seletor e marque compartilhar áudio, quando disponível.' : 'A captura é local. Somente as pessoas que assistem recebem a transmissão.'}<br/>{source === 'browser' && audio !== 'none' && <small>Para evitar eco da chamada, prefira compartilhar uma aba ou janela com áudio próprio. Ao escolher tela inteira, o navegador pode incluir áudio de outros apps; a proteção desta página cobre apenas o som da própria aba quando suportada.</small>}<small>A resolução mantém a proporção e não amplia uma fonte menor. Preservar resolução prioriza a nitidez; FPS e entrega dependem da fonte, hardware e rede. O upload informado é dividido entre todas as cópias enviadas.</small></p></details>
            {room.capturing ? <button disabled><ScreenShare size={18}/>Preparando…</button> : <button className="room-primary" disabled={!connected || (source === 'browser' && !support.screen) || (source === 'camera' && !support.camera) || room.locals.length >= MAX_LOCAL_STREAMS || (nativeBusy && (source === 'window' || source === 'monitor' || source === 'game' || audio === 'process'))} onClick={share}><ScreenShare size={18}/>{source === 'camera' ? 'Adicionar câmera' : 'Compartilhar tela'}</button>}

          </div>
          {room.locals.map(local => <div className="room-local-source" key={local.id}><span>{local.title} · {local.kind === 'camera' ? 'Câmera' : 'Tela'} · Alvo {QUALITY_PRESETS[local.quality.resolution].label} · {local.quality.fps || 'Auto'} FPS{local.warning && <small role="status">{local.warning}</small>}</span><button className="room-danger" onClick={() => void room.stop(local.id)} aria-label={`Parar ${local.title}`}><Square size={14}/>Parar</button></div>)}
        </div>
    </div>
  </dialog>;
}
