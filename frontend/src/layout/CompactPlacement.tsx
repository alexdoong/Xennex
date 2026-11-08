import { useEffect, useRef, useState } from 'react';

export default function CompactPlacement({ position }: { position: string }) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [inset, setInset] = useState(0);
  const [vertical, setVertical] = useState(50);
  const [collapseEdge, setCollapseEdge] = useState('Auto');
  const [animationFps, setAnimationFps] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let disposed = false;
    if (api) {
      Promise.all([
        api.GetSidebarInset(),
        api.GetSidebarVerticalPercent(),
        api.GetSidebarCollapseEdge?.() ?? Promise.resolve('Auto'),
        api.GetSidebarAnimationFps?.() ?? Promise.resolve(0)
      ]).then(([gap, height, edge, fps]) => {
        if (disposed) return;
        setInset(gap);
        setVertical(height < 0 ? (position === 'TopLeft' ? 0 : 50) : height);
        setCollapseEdge(edge || 'Auto');
        setAnimationFps(fps);
      }).catch(() => {
        if (!disposed) setMessage('Não foi possível ler a posição salva.');
      });
    }
    return () => { disposed = true; };
  }, [api, position]);

  async function save(reset = false) {
    if (busy || !api) return;
    setBusy(true);
    setMessage('');
    try {
      const nextEdge = reset ? 'Auto' : collapseEdge;
      await api.SetSidebarPlacement(reset ? 0 : inset, reset ? -1 : vertical);
      if (api.SetSidebarCollapseEdge) {
        await api.SetSidebarCollapseEdge(nextEdge);
      }
      await api.SetSidebarAnimationFps(reset ? 0 : animationFps);
      window.updateSidebarCollapseEdge?.(nextEdge);
      if (reset) {
        setInset(0);
        setVertical(position === 'TopLeft' ? 0 : 50);
        setCollapseEdge('Auto');
        setAnimationFps(0);
      }
      setMessage('Posição salva.');
    } catch {
      setMessage('Não foi possível salvar a posição.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="compact-placement">
      <summary>Ajustar posição</summary>
      <p>Afaste o painel da borda e escolha a direção para onde ele deve se recolher.</p>
      <form onSubmit={e => { e.preventDefault(); void save(); }}>
        <fieldset disabled={busy}>
          <label>Recolher para
            <select
              aria-label="Direção de recolhimento"
              value={collapseEdge}
              onChange={e => setCollapseEdge(e.target.value)}
            >
              <option value="Auto">Automático (borda mais próxima)</option>
              <option value="Top">Topo (Alça horizontal)</option>
              <option value="Left">Borda esquerda</option>
              <option value="Right">Borda direita</option>
            </select>
          </label>
          <label>FPS da animação
            <select aria-label="FPS da animação" value={animationFps} onChange={e => setAnimationFps(Number(e.target.value))}>
              <option value="0">Automático (acompanhar renderização)</option>
              <option value="30">30 FPS</option>
              <option value="60">60 FPS</option>
              <option value="120">120 FPS</option>
            </select>
          </label>
          <p>Limite de quadros; a fluidez também depende do monitor e da carga do PC.</p>
          <label>Distância da lateral (px)
            <input
              type="number"
              min="0"
              max="2000"
              step="1"
              required
              value={inset}
              onChange={e => setInset(Math.max(0, Math.min(2000, Number(e.target.value))))}
            />
          </label>
          <label>Altura na tela · {vertical}%
            <input
              aria-label="Altura na tela"
              type="range"
              min="0"
              max="100"
              step="1"
              value={vertical}
              onChange={e => setVertical(Number(e.target.value))}
            />
          </label>
          <div className="compact-placement-ends"><span>Topo</span><span>Base</span></div>
          <div className="compact-placement-actions">
            <button className="btn primary" type="submit">{busy ? 'Salvando…' : 'Aplicar posição'}</button>
            <button className="btn secondary" type="button" onClick={() => void save(true)}>Restaurar</button>
          </div>
        </fieldset>
      </form>
      <p role="status">{message || 'O limite do monitor mantém o painel visível.'}</p>
    </details>
  );
}
