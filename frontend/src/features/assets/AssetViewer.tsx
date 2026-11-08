import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Minus, Plus, X } from 'lucide-react';
import type { AssetItem } from './types';
import { mediaUrl } from './types';

type Props = { items: AssetItem[]; initialId: string; onClose: () => void };

export default function AssetViewer({ items, initialId, onClose }: Props) {
  const [index, setIndex] = useState(() => Math.max(0, items.findIndex(item => item.id === initialId)));
  const [zoom, setZoom] = useState(1);
  const item = items[index];
  useEffect(() => {
    function key(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
      if (event.key === 'ArrowLeft') setIndex(value => Math.max(0, value - 1));
      if (event.key === 'ArrowRight') setIndex(value => Math.min(items.length - 1, value + 1));
    }
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [items.length, onClose]);
  if (!item) return null;
  return <div className="assets-viewer" role="dialog" aria-modal="true" aria-label={`Visualizar ${item.name}`}>
    <div className="assets-viewer-bar">
      <strong>{item.name}</strong><span>{index + 1} / {items.length}</span>
      <button className="title-btn" onClick={() => setZoom(value => Math.max(.5, value - .25))} title="Diminuir zoom"><Minus size={18}/></button>
      <button className="title-btn" onClick={() => setZoom(1)} title="Ajustar à tela">{Math.round(zoom * 100)}%</button>
      <button className="title-btn" onClick={() => setZoom(value => Math.min(4, value + .25))} title="Aumentar zoom"><Plus size={18}/></button>
      <button className="title-btn" onClick={onClose} title="Fechar"><X size={20}/></button>
    </div>
    <div className="assets-viewer-content">
      <div className="assets-viewer-image"><img src={mediaUrl(item, 'preview')} alt={item.name} style={{ transform: `scale(${zoom})` }} draggable={false}/></div>
    </div>
    <div className="assets-viewer-navigation" role="group" aria-label="Navegar entre imagens">
      <button className="title-btn" disabled={index === 0} onClick={() => { setIndex(index - 1); setZoom(1); }} aria-label="Imagem anterior"><ChevronLeft/></button>
      <span>{index + 1} / {items.length}</span>
      <button className="title-btn" disabled={index === items.length - 1} onClick={() => { setIndex(index + 1); setZoom(1); }} aria-label="Próxima imagem"><ChevronRight/></button>
    </div>
  </div>;
}
