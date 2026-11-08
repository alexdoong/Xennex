import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Folder, FolderOpen, RefreshCw } from 'lucide-react';
import type { AssetItem, AssetPage, AssetRoot } from './types';

type Props = {
  roots: AssetRoot[];
  rootId: string;
  folder: string;
  onChange: (rootId: string, folder: string) => void;
};

export default function AssetDestinationPicker({ roots, rootId, folder, onChange }: Props) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [directories, setDirectories] = useState<AssetItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [revision, setRevision] = useState(0);
  const request = useRef(0);
  const root = roots.find(value => value.id === rootId);

  useEffect(() => { setDirectories([]); setOffset(0); setTotal(0); setFilter(''); }, [rootId, folder]);
  useEffect(() => {
    if (!api || !rootId) return;
    const current = ++request.current;
    let disposed = false;
    const load = async () => {
      setLoading(true); setError('');
      try {
        const result = JSON.parse(await api.QueryAssets(JSON.stringify({ rootId, folder, directoriesOnly: true,
          includeDescendants: false, sort: 'name', offset, limit: 200 }))) as AssetPage;
        if (disposed || current !== request.current) return;
        setDirectories(previous => offset === 0 ? result.items.filter(item => item.isDirectory) :
          [...previous, ...result.items.filter(item => item.isDirectory)]);
        setTotal(result.total);
      } catch (reason) { if (!disposed && current === request.current) setError(String(reason)); }
      finally { if (!disposed && current === request.current) setLoading(false); }
    };
    void load();
    return () => { disposed = true; };
  }, [api, rootId, folder, offset, revision]);

  const parts = folder ? folder.split('/') : [];
  const filtered = directories.filter(item => item.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  return <div className="assets-destination-picker">
    <strong>Escolha a pasta de destino</strong>
    <div className="assets-destination-roots" role="group" aria-label="Pastas cadastradas">
      {roots.filter(value => value.online).map(value => <button key={value.id} className={rootId === value.id ? 'active' : ''}
        title={value.path} onClick={() => onChange(value.id, '')}><Folder size={15}/>{value.path.split(/[\\/]/).at(-1) || value.path}</button>)}
    </div>
    <nav className="assets-destination-path" aria-label="Pasta de destino">
      <button onClick={() => onChange(rootId, '')}>{root?.path || 'Acervo'}</button>
      {parts.map((part, index) => <span key={index}> / <button onClick={() => onChange(rootId, parts.slice(0, index + 1).join('/'))}>{part}</button></span>)}
    </nav>
    <p>Destino selecionado: <strong>{root?.path}{folder ? '\\' + folder.replaceAll('/', '\\') : ''}</strong></p>
    <div className="assets-destination-tools">
      <button className="btn secondary" disabled={!folder} onClick={() => onChange(rootId, parts.slice(0, -1).join('/'))}><ArrowLeft size={15}/> Voltar</button>
      <input aria-label="Filtrar subpastas visíveis" placeholder="Filtrar subpastas desta pasta" value={filter} onChange={event => setFilter(event.target.value)}/>
      <button className="title-btn" title="Atualizar pastas" onClick={() => { setOffset(0); setRevision(value => value + 1); }}><RefreshCw size={16}/></button>
    </div>
    {error && <p role="alert" className="assets-alert">{error}</p>}
    <div className="assets-destination-list" role="list" aria-label="Subpastas disponíveis">
      {filtered.map(item => <button role="listitem" key={item.id} onClick={() => onChange(rootId, item.relativePath)}><FolderOpen size={17}/><span>{item.name}</span></button>)}
      {!loading && !filtered.length && <small>{filter ? 'Nenhuma subpasta com esse nome foi carregada.' : 'Nenhuma subpasta aqui. Você pode usar esta pasta como destino.'}</small>}
      {loading && <small>Carregando pastas…</small>}
    </div>
    {offset + 200 < total && <button className="btn secondary" disabled={loading} onClick={() => setOffset(value => value + 200)}>Carregar mais itens</button>}
  </div>;
}
