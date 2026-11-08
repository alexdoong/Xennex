import { useState } from 'react';
import { Minus, Plus, X } from 'lucide-react';
import type { AssetItem } from './types';
import { mediaUrl } from './types';

export default function AssetCompare({ items, onClose }: { items: AssetItem[]; onClose: () => void }) {
  const [sync, setSync] = useState(false);
  const [zoom, setZoom] = useState<Record<string, number>>({});
  const changeZoom = (id: string, delta: number) => setZoom(previous => {
    const next = { ...previous };
    const value = Math.max(.5, Math.min(4, (previous[id] || 1) + delta));
    if (sync) for (const item of items) next[item.id] = value;
    else next[id] = value;
    return next;
  });
  return <div className="assets-compare" role="dialog" aria-modal="true" aria-label="Comparar artes">
    <header><h2>Comparar artes</h2><span>{items.length} imagens</span><label><input type="checkbox" checked={sync} onChange={event => setSync(event.target.checked)}/> Sincronizar zoom</label><button className="title-btn" onClick={onClose} aria-label="Fechar comparação"><X/></button></header>
    <div className="assets-compare-grid">{items.map(item => <figure key={item.id}>
      <div className="assets-compare-image"><img src={mediaUrl(item, 'preview')} alt={item.name} style={{ transform: `scale(${zoom[item.id] || 1})` }}/></div>
      <figcaption><span>{item.name}</span><button className="title-btn" title={`Diminuir zoom de ${item.name}`} onClick={() => changeZoom(item.id, -.25)}><Minus size={16}/></button>
        {Math.round((zoom[item.id] || 1) * 100)}%
        <button className="title-btn" title={`Aumentar zoom de ${item.name}`} onClick={() => changeZoom(item.id, .25)}><Plus size={16}/></button></figcaption>
    </figure>)}</div>
  </div>;
}
