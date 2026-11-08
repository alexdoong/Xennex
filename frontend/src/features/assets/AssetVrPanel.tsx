import { useCallback, useEffect, useRef, useState } from 'react';
import { Glasses, X } from 'lucide-react';
import type { AssetItem, AssetQuery, AssetView } from './types';

type VrState = { state: 'stopped' | 'starting' | 'running' | 'failed'; error: string; count: number; index: number; name: string; zoom: number; pinned: boolean; view: string; location: string; canPrevious: boolean; canNext: boolean; widthMeters: number; distanceMeters: number };
const stopped: VrState = { state: 'stopped', error: '', count: 0, index: 0, name: '', zoom: 1, pinned: false, view: 'image', location: '', canPrevious: false, canNext: false, widthMeters: 2, distanceMeters: 1.5 };

export default function AssetVrPanel({ items, query, view, onClose }: { items: AssetItem[]; query: AssetQuery; view: AssetView; onClose: () => void }) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [state, setState] = useState(stopped);
  const [hideWindow, setHideWindow] = useState(true);
  const [mode, setMode] = useState<'library' | 'selection'>('library');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const revision = useRef(0);
  const mounted = useRef(true);
  const refresh = useCallback(async () => {
    if (!api) return;
    const current = ++revision.current;
    const result = JSON.parse(await api.GetAssetVrState()) as VrState;
    if (mounted.current && current === revision.current) setState(result);
  }, [api]);

  useEffect(() => {
    mounted.current = true;
    if (busy) return () => { mounted.current = false; };
    const poll = () => { void refresh().catch(reason => { if (mounted.current) setError(String(reason)); }); };
    poll();
    const timer = window.setInterval(poll, 1000);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, [refresh, busy]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [busy, onClose]);

  const run = async (action: () => Promise<void>) => {
    if (!api || busy) return;
    setBusy(true); ++revision.current; setError('');
    try { await action(); }
    catch (reason) { if (mounted.current) setError(String(reason)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const start = () => run(async () => {
    const result = JSON.parse(await api!.StartAssetVr(JSON.stringify({ mode, query, view, assetIds: items.map(item => item.id), initialId: items[0]?.id || '' }))) as VrState;
    if (!mounted.current) return;
    setState(result);
    if (result.state === 'running' && hideWindow) await api!.MinimizeToTray();
  });
  const control = (action: string) => run(async () => { await api!.ControlAssetVr(action); });
  const running = state.state === 'running';
  return <div className="assets-operation-overlay" onMouseDown={event => { if (!busy && event.target === event.currentTarget) onClose(); }}>
    <section className="assets-operation assets-vr-panel" role="dialog" aria-modal="true" aria-label="Biblioteca no VR">
      <header><h2><Glasses size={21}/> Biblioteca no VR</h2><button className="title-btn" disabled={busy} onClick={onClose} aria-label="Fechar opções de VR"><X size={18}/></button></header>
      <p>Navegue pela galeria, pelos arquivos e pelas pastas cadastradas dentro do SteamVR. Use o gatilho para abrir miniaturas e os botões Anterior/Próxima para mudar de imagem ou página.</p>
      <label>Conteúdo do painel <select aria-label="Conteúdo do painel VR" value={mode} disabled={busy || running} onChange={event => setMode(event.target.value as 'library' | 'selection')}>
        <option value="library">Biblioteca completa — começar na visão atual</option>
        <option value="selection" disabled={!items.length}>Seleção atual — {items.length} imagens</option>
      </select></label>
      <p>A Biblioteca mantém os filtros atuais ao abrir. No headset, use Acervos para escolher outra pasta, Galeria para ver as artes e Explorador para navegar pelos arquivos. Edição e movimentação continuam no desktop.</p>
      <p>O painel começa maior. Use Tamanho dentro do headset para aumentar a largura ou aproximar o painel fixado. Esses ajustes são diferentes do zoom da imagem.</p>
      <p>Deixe SteamVR e Meta Link abertos com o headset conectado. O Xennex continua funcionando na bandeja.</p>
      <p className="assets-vr-privacy">O Xennex não abre um espelho no monitor. Oculus Mirror e capturas do SteamVR ainda podem mostrar o conteúdo do headset.</p>
      <label className="assets-vr-hide"><input type="checkbox" checked={hideWindow} onChange={event => setHideWindow(event.target.checked)} disabled={busy || running}/> Minimizar o Xennex à bandeja após abrir no VR</label>
      {(error || state.error || !api) && <p role="alert">{error || state.error || 'Abra esta opção pelo aplicativo Xennex atualizado.'}</p>}
      <div className="assets-vr-status" role="status">{running ? state.view === 'image' ? `${state.index + 1} / ${state.count} · ${state.name} · Zoom ${Math.round(state.zoom * 100)}%` : `${state.location} · ${state.count} itens · Página ${Math.floor(state.index / 12) + 1}` : busy || state.state === 'starting' ? 'Conectando ao painel…' : state.state === 'failed' ? 'Não foi possível abrir o painel.' : 'Painel fechado'}</div>
      {running && <div className="assets-vr-controls">
        <button className="btn secondary" disabled={busy || !state.canPrevious} onClick={() => void control('previous')}>Anterior</button>
        <button className="btn secondary" disabled={busy || !state.canNext} onClick={() => void control('next')}>Próxima</button>
        {mode === 'library' && <><button className="btn secondary" disabled={busy} onClick={() => void control('gallery')}>Galeria</button><button className="btn secondary" disabled={busy} onClick={() => void control('explorer')}>Explorador</button><button className="btn secondary" disabled={busy} onClick={() => void control('roots')}>Acervos</button><button className="btn secondary" disabled={busy} onClick={() => void control('back')}>Voltar</button></>}
        <button className="btn secondary" disabled={busy} onClick={() => void control('zoomOut')}>Zoom −</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('fit')}>Ajustar</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('zoomIn')}>Zoom +</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('pin')}>{state.pinned ? 'Voltar ao dashboard' : 'Fixar no espaço'}</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('recenter')}>Centralizar</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('panel')}>Tamanho do painel</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('sizeDown')}>Diminuir painel</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('sizeUp')}>Aumentar painel</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('nearer')}>Mais perto</button>
        <button className="btn secondary" disabled={busy} onClick={() => void control('farther')}>Mais longe</button>
      </div>}
      <div className="assets-operation-buttons"><button className="btn secondary" disabled={busy} onClick={onClose}>Voltar à Biblioteca</button>
        {running ? <button className="btn primary" disabled={busy} onClick={() => void run(async () => { await api!.StopAssetVr(); setState(stopped); })}>Encerrar VR</button>
          : <button className="btn primary" disabled={!api || mode === 'selection' && !items.length || busy || state.state === 'starting'} onClick={() => void start()}>Abrir no SteamVR</button>}
      </div>
      <small>Fechar estas opções mantém o painel aberto. Encerrar VR fecha apenas o painel e não revela a janela no monitor.</small>
    </section>
  </div>;
}
