import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Heart, Images } from 'lucide-react';
import type { AppTab } from '../../layout/navigation';
import type { AssetItem, AssetPage, AssetRoot } from './types';
import { mediaUrl } from './types';

export default function AssetsCompact({ openFullWindow }: { openFullWindow: (tab?: AppTab) => void }) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [items, setItems] = useState<AssetItem[]>([]);
  const [roots, setRoots] = useState<AssetRoot[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    Promise.all([api.GetAssetRoots(), api.QueryAssets(JSON.stringify({ imagesOnly: true, includeDescendants: true, sort: 'date', limit: 12 }))])
      .then(([rootJson, pageJson]) => { if (!cancelled) { setRoots(JSON.parse(rootJson) as AssetRoot[]); setItems((JSON.parse(pageJson) as AssetPage).items); } })
      .catch(reason => { if (!cancelled) setError(String(reason)); });
    return () => { cancelled = true; };
  }, [api]);
  return <div className="assets-compact">
    <p>Seu acervo <strong>{roots.length} pastas</strong></p>
    {error && <p role="alert">{error}</p>}
    <div className="assets-compact-strip">{items.map(item => <button key={item.id} title={item.name} onClick={() => openFullWindow('assets')}><img src={mediaUrl(item, 'thumb')} alt={item.name}/>{item.favorite && <Heart size={13}/>}</button>)}</div>
    {!items.length && <p>Adicione uma pasta na janela completa para ver suas artes aqui.</p>}
    <button className="btn primary" onClick={() => openFullWindow('assets')}><Images size={17}/> Abrir Biblioteca <ArrowUpRight size={17}/></button>
  </div>;
}
