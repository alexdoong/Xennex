import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Search, X } from 'lucide-react';
import type { AssetTagOverviewPage } from './types';

export type AssetTagSource = 'all' | 'manual' | 'positive' | 'negative';
type Props = { onClose: () => void; onPick: (term: string, source: AssetTagSource) => void };
const empty: AssetTagOverviewPage = { items: [], total: 0, nextOffset: 0 };

export default function AssetTagBrowser({ onClose, onPick }: Props) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [source, setSource] = useState<AssetTagSource>('all');
  const [search, setSearch] = useState('');
  const [querySearch, setQuerySearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const request = useRef(0);
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => { searchInput.current?.focus(); }, []);
  useEffect(() => { const timer = window.setTimeout(() => setQuerySearch(search), 180); return () => window.clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!api) { setLoading(false); setError('O catálogo de tags está disponível no aplicativo para Windows.'); return; }
    const current = ++request.current;
    setLoading(true); setError('');
    void api.GetAssetTagOverview(JSON.stringify({ source, search: querySearch, offset, limit: 100 }))
      .then(value => { if (current === request.current) setPage(JSON.parse(value) as AssetTagOverviewPage); })
      .catch(reason => { if (current === request.current) setError(String(reason)); })
      .finally(() => { if (current === request.current) setLoading(false); });
  }, [api, source, querySearch, offset, revision]);
  const chooseSource = (value: AssetTagSource) => { setSource(value); setOffset(0); };
  return <div className="assets-operation-overlay" role="presentation"
    onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}
    onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } }}>
    <section className="assets-tag-browser" role="dialog" aria-modal="true" aria-label="Todas as tags">
      <header><div><small>ACERVO COMPLETO</small><h2>Todas as tags</h2></div>
        <button className="title-btn" onClick={onClose} aria-label="Fechar todas as tags"><X size={20}/></button></header>
      <p>Etiquetas manuais e termos extraídos dos prompts. Positivo/negativo descreve a entrada da geração, não a qualidade da imagem.</p>
      <div className="assets-tag-browser-tools"><label><Search size={16}/><input ref={searchInput} value={search} maxLength={100}
        onChange={event => { setSearch(event.target.value); setOffset(0); }} placeholder="Buscar tag ou termo" aria-label="Buscar tags"/></label>
        <button className="title-btn" title="Atualizar tags" onClick={() => setRevision(value => value + 1)}><RefreshCw size={17}/></button></div>
      <nav role="tablist" aria-label="Origem das tags">
        {([['all','Juntas'],['manual','Manuais'],['positive','Prompt positivo'],['negative','Prompt negativo']] as const)
          .map(([value, label]) => <button key={value} role="tab" aria-selected={source === value} onClick={() => chooseSource(value)}>{label}</button>)}
      </nav>
      <div className="assets-tag-browser-results" role="tabpanel" aria-label="Tags encontradas">
        {loading && <p role="status">Lendo as tags do catálogo…</p>}
        {error && <p role="alert">{error}</p>}
        {!loading && !error && !page.items.length && <p>Nenhuma tag encontrada nesta origem.</p>}
        {!loading && page.items.map(item => <div className="assets-tag-browser-row" key={item.term}>
          <button className="assets-tag-browser-term" onClick={() => onPick(item.term, source)} title={`Filtrar por ${item.term}`}>{item.term}</button>
          <div className="assets-tag-browser-sources">
            {item.manual > 0 && <button onClick={() => onPick(item.term, 'manual')} title="Filtrar etiquetas manuais">Manual {item.manual}</button>}
            {item.positive > 0 && <button onClick={() => onPick(item.term, 'positive')} title="Filtrar prompt positivo">Positivo {item.positive}</button>}
            {item.negative > 0 && <button onClick={() => onPick(item.term, 'negative')} title="Filtrar prompt negativo">Negativo {item.negative}</button>}
          </div>
        </div>)}
      </div>
      <footer><span>{page.total} termos · {page.items.length ? `${offset + 1}–${page.nextOffset}` : '0'}</span>
        <div><button className="btn secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Anterior</button>
          <button className="btn secondary" disabled={loading || page.nextOffset >= page.total} onClick={() => setOffset(page.nextOffset)}>Próxima</button></div></footer>
    </section>
  </div>;
}
