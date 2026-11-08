import { useState } from 'react';
import { GestureEditor } from './GestureEditor';
import { LandmarkPreview } from './LandmarkPreview';
import { useGesturesContext } from './GesturesContext';
import type { GestureBinding } from './types';


export default function HandMotionTab(_props: { handMotionStatus: boolean }) {
  const { api, profile, status, camera, setCamera, error, busy, dirty, edit, run, save } = useGesturesContext();
  const [newName, setNewName] = useState('');
  const [newSource, setNewSource] = useState<'pose' | 'motion'>('pose');
  const locked = busy || status.armed || !!status.recording;
  const change = (gesture: GestureBinding) => {
    if (profile) edit({ ...profile, gestures: profile.gestures.map(g => g.id === gesture.id ? gesture : g) });
  };
  function add() {
    if (!profile || !newName.trim()) return;
    edit({ ...profile, gestures: [...profile.gestures, {
      id: crypto.randomUUID(), name: newName.trim(), source: newSource, enabled: true,
      holdMs: 300, cooldownMs: 1200, threshold: .22, action: { type: 'none', value: '' }, samples: [],
    }] });
    setNewName('');
  }
  return <section className="glass-panel gestures-page">
    <header><h1>Gestures</h1><p>Transforme poses e movimentos da mão em ações no computador.</p></header>
    {!api && <p className="gestures-notice">O controle do computador está disponível no aplicativo Windows.</p>}
    {error && <p role="alert" className="gestures-error">{error}</p>}
    <div className="gestures-toolbar">
      <button className="btn primary" disabled={!api || busy || !!status.recording} onClick={() => void run(async () => {
        if (status.running) await api!.StopHandMotion();
        else { await api!.SetHandMotionCameraIndex(camera); await api!.StartHandMotion(); }
      })}>{status.running ? 'Desligar câmera' : 'Iniciar câmera em teste'}</button>
      <button className={status.armed ? 'btn danger' : 'btn secondary'} disabled={!status.running || busy || !!status.recording || dirty} onClick={() => void run(() => api!.SetGestureControl(!status.armed))}>
        {status.armed ? 'Pausar controle' : 'Ativar controle do PC'}
      </button>
      <button className="btn secondary" disabled={!profile || !dirty || locked} onClick={() => void run(save)}>Salvar alterações{dirty ? ' •' : ''}</button>
    </div>
    <div className="gestures-monitor">
      <LandmarkPreview points={status.points} />
      <div>
        <span className="gestures-tag">{status.armed ? 'CONTROLANDO O PC' : status.running ? 'MODO DE TESTE' : 'CÂMERA DESLIGADA'}</span>
        <p role="status">{status.message}</p>
        <p>Mão: {status.points ? (status.hand === 'Left' ? 'esquerda' : 'direita') : 'não detectada'}<br />
          Último gesto: <strong>{status.match || 'aguardando'}</strong></p>
        {status.running && status.metrics && <p className="gestures-notice">Captura processada: {status.metrics.fps.toFixed(0)} FPS · Visão: {status.metrics.inferenceMs.toFixed(0)} ms · Idade do quadro: {status.metrics.frameAgeMs.toFixed(0)} ms</p>}
        {status.recording ? <div className="gestures-notice" aria-live="polite">
          <strong>{status.stage === 'countdown' ? 'Prepare a mão' : 'Gravando'}: {status.remaining ?? 0}s</strong>
          <p>Faça somente o gesto escolhido. As ações estão pausadas.</p>
          <button className="btn secondary" disabled={busy} onClick={() => void run(() => api!.CancelGestureRecording())}>Cancelar gravação</button>
        </div> : <p><kbd>Esc</kbd> pausa os comandos. Tirar a mão da câmera solta o arraste.<br />No modo de teste, nenhum atalho ou movimento é executado.</p>}
      </div>
    </div>
    {profile && <>
      {profile.migrationNotice && <p className="gestures-notice">{profile.migrationNotice}</p>}
      <fieldset className="gestures-settings" disabled={locked}>
        <legend>Câmera e controle</legend>
        <div className="gestures-fields">
          <label>Índice da câmera<input type="number" min="0" max="20" value={camera} disabled={status.running} onChange={e => setCamera(Math.max(0, Math.min(20, Number(e.target.value))))} /><small>0 = primeira câmera; altere com a câmera desligada.</small></label>
          <label>Mão<select value={profile.hand} onChange={e => edit({ ...profile, hand: e.target.value as typeof profile.hand })}>
            <option value="Any">Qualquer mão (uma por vez)</option><option value="Left">Esquerda</option><option value="Right">Direita</option>
          </select></label>
          <label>Janela segurada pelo pinch<select value={profile.dragTarget} onChange={e => edit({ ...profile, dragTarget: e.target.value as typeof profile.dragTarget })}>
            <option value="titlebar">Barra de título sob o indicador</option><option value="foreground">Janela ativa</option>
          </select></label>
          <label>Suavização: {Math.round(profile.smoothing * 100)}%<input type="range" min="0" max=".9" step=".05" value={profile.smoothing} onChange={e => edit({ ...profile, smoothing: Number(e.target.value) })} /></label>
          <label>Distância mínima de swipe: {Math.round(profile.swipeThreshold * 100)}%<input type="range" min=".08" max=".5" step=".01" value={profile.swipeThreshold} onChange={e => edit({ ...profile, swipeThreshold: Number(e.target.value) })} /></label>
        </div>
        <p><label className="gestures-check"><input type="checkbox" checked={profile.preview} onChange={e => edit({ ...profile, preview: e.target.checked })} />Abrir vídeo da câmera em uma janela de prévia</label></p>
      </fieldset>
      <p className="gestures-notice">Aponte o indicador para mover o cursor. Faça pinch para segurar uma janela restaurada e abra os dedos para soltá-la.
        Para os swipes, mova a palma aberta. Pause os controles para editar os gestos.</p>
      <h2>Seus gestos</h2>
      <p>Crie uma pose ou um movimento, salve e grave exemplos. Comece com três amostras semelhantes.
        A memória guarda os pontos da mão, sem fotos ou vídeos.</p>
      <fieldset className="gestures-settings gestures-create" disabled={locked || profile.gestures.length >= 40}>
        <legend>Novo gesto</legend>
        <label>Nome<input maxLength={80} placeholder="Ex.: fechar a mão para pausar" value={newName} onChange={e => setNewName(e.target.value)} /></label>
        <label>Tipo<select value={newSource} onChange={e => setNewSource(e.target.value as 'pose' | 'motion')}><option value="pose">Pose parada</option><option value="motion">Movimento</option></select></label>
        <button className="btn secondary" disabled={!newName.trim()} onClick={add}>Adicionar gesto</button>
      </fieldset>
      <div className="gestures-grid">{profile.gestures.map(gesture => <GestureEditor key={gesture.id} gesture={gesture}
        disabled={locked} canRecord={status.running} change={change}
        record={() => void run(async () => { await save(); await api!.RecordGestureSample(gesture.id); })}
        clear={() => void run(async () => { await save(); await api!.ClearGestureSamples(gesture.id); })}
        remove={() => edit({ ...profile, gestures: profile.gestures.filter(g => g.id !== gesture.id) })} />)}</div>
      <p><small>A base atual reconhece mãos. Poses do corpo e palmas ficam para uma extensão futura do rastreador.
        Gestos parecidos podem se confundir; desabilite os padrões que competirem com os seus.</small></p>
    </>}
  </section>;
}
