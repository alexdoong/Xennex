import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Folder, RefreshCw, X } from 'lucide-react';
import type { AssetItem, AssetPage, AssetRoot } from './types';
import { mediaUrl } from './types';

type Props = { roots: AssetRoot[]; rootId: string; folder: string; onRoot: (id: string) => void; onFolder: (path: string) => void;
  selectedCount: number; onCopy: () => void; onMove: () => void; onClose: () => void };

export default function AssetSecondaryPane({ roots, rootId, folder, onRoot, onFolder, selectedCount, onCopy, onMove, onClose }: Props) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [items, setItems] = useState<AssetItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const load = useCallback(async () => {
    if (!api || !rootId) { setItems([]); setTotal(0); return; }
    const result = JSON.parse(await api.QueryAssets(JSON.stringify({ rootId, folder, imagesOnly: false,
      includeDescendants: false, sort: 'name', offset: 0, limit: 100 }))) as AssetPage;
    setItems(result.items); setTotal(result.total); setError('');
  }, [api, rootId, folder]);
  useEffect(() => { void load().catch(reason => setError(String(reason))); }, [load, revision]);
  const root = roots.find(value => value.id === rootId);
  return <section className="assets-secondary-pane" aria-label="Segundo painel de arquivos">
    <header><strong>Segundo painel</strong><div className="assets-pane-actions"><button className="title-btn" title="Atualizar segundo painel" onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/></button>
      <button className="title-btn" title="Fechar segundo painel" aria-label="Fechar segundo painel" onClick={onClose}><X size={16}/></button></div></header>
    <select aria-label="Pasta do segundo painel" value={rootId} onChange={event => { onRoot(event.target.value); onFolder(''); }}>
      {roots.map(value => <option key={value.id} value={value.id}>{value.path}</option>)}
    </select>
    <div className="assets-second-path"><button onClick={() => onFolder('')}>{root?.path.split(/[\\/]/).at(-1) || 'Pasta'}</button>
      {folder && <><span> / {folder}</span><button title="Voltar uma pasta" onClick={() => onFolder(folder.split('/').slice(0, -1).join('/'))}><ArrowLeft size={15}/></button></>}</div>
    {error && <p role="alert">{error}</p>}
    <div className="assets-second-list">{items.map(item => <button key={item.id} title={item.relativePath} onDoubleClick={() => { if (item.isDirectory) onFolder(item.relativePath); }}
      onClick={() => { if (item.isDirectory) onFolder(item.relativePath); }}>
      {item.isImage ? <img src={mediaUrl(item, 'thumb')} alt=""/> : <Folder size={18}/>}<span>{item.name}</span>
    </button>)}
      {total > items.length && <small>Exibindo os primeiros {items.length} de {total} itens.</small>}
    </div>
    <footer><span>{selectedCount} no painel principal</span>
      <button className="btn secondary" disabled={!selectedCount || !rootId} onClick={onCopy}>Copiar aqui</button>
      <button className="btn secondary" disabled={!selectedCount || !rootId} onClick={onMove}>Mover aqui</button>
    </footer>
  </section>;
}
