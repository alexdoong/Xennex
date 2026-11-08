import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Copy, Download, Folder, FolderPlus, Grid2X2, Heart, Images, List, Maximize2, Minimize2, Pencil, Plus, RefreshCw, Search, Tag, Trash2, X } from 'lucide-react';
import AssetViewer from './AssetViewer';
import AssetVrPanel from './AssetVrPanel';
import AssetCompare from './AssetCompare';
import AssetFileActions from './AssetFileActions';
import AssetSecondaryPane from './AssetSecondaryPane';
import AssetBulkEditor, { type AssetBulkChanges } from './AssetBulkEditor';
import AssetGenerationModal from './AssetGenerationModal';
import AssetTagBrowser, { type AssetTagSource } from './AssetTagBrowser';
import { parseImageMetadata } from './comfyMetadata';
import { mediaUrl, type AssetCollection, type AssetItem, type AssetJob, type AssetOperation, type AssetPage, type AssetQuery, type AssetRelinkPlan, type AssetRoot, type AssetRule, type AssetView, type SavedAssetQuery } from './types';

const saved = (key: string) => { try { return localStorage.getItem('assets.' + key) || ''; } catch { return ''; } };
const remember = (key: string, value: string) => { try { localStorage.setItem('assets.' + key, value); } catch { /* storage optional */ } };
const readableSize = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
type RuleRow = { field: string; comparison: string; value: string; negate: boolean };
type WorkspaceTab = { id: string; rootId: string; folder: string; view: AssetView };
const newRule = (): RuleRow => ({ field: 'metadata', comparison: 'contains', value: '', negate: false });
const isMissingBridge = (reason: unknown) => /0x80020006|nome desconhecido|unknown name/i.test(String(reason));
const bridgeError = (reason: unknown) => isMissingBridge(reason)
  ? 'A interface da Biblioteca está mais recente que o executável aberto. Feche o Xennex antigo e abra o build atualizado com scripts/run_dev.ps1.'
  : String(reason);

export default function AssetLibraryTab({ active }: { active: boolean }) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [roots, setRoots] = useState<AssetRoot[]>([]);
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [savedQueries, setSavedQueries] = useState<SavedAssetQuery[]>([]);
  const [operations, setOperations] = useState<AssetOperation[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [rootId, setRootId] = useState(saved('root'));
  const [folder, setFolder] = useState(saved('folder'));
  const [view, setView] = useState<AssetView>(saved('view') === 'explorer' ? 'explorer' : 'gallery');
  const [tileSize, setTileSize] = useState(() => Math.max(120, Math.min(260, Number(saved('tileSize')) || 160)));
  const [crop, setCrop] = useState(saved('crop') === 'true');
  const [workspaceTabs, setWorkspaceTabs] = useState<WorkspaceTab[]>(() => [{ id: crypto.randomUUID(), rootId: saved('root'), folder: saved('folder'), view: saved('view') === 'explorer' ? 'explorer' : 'gallery' }]);
  const [activeWorkspace, setActiveWorkspace] = useState(() => workspaceTabs[0].id);
  const [dualPane, setDualPane] = useState(false);
  const [splitDirection, setSplitDirection] = useState<'columns' | 'rows'>(saved('splitDirection') === 'rows' ? 'rows' : 'columns');
  const [splitRatio, setSplitRatio] = useState(() => Math.max(25, Math.min(75, Number(saved('splitRatio')) || 50)));
  const [expanded, setExpanded] = useState(saved('expanded') === 'true');
  const [secondRootId, setSecondRootId] = useState(saved('secondRoot'));
  const [secondFolder, setSecondFolder] = useState(saved('secondFolder'));
  const [operationTarget, setOperationTarget] = useState(false);
  const [search, setSearch] = useState('');
  const [querySearch, setQuerySearch] = useState('');
  const [tag, setTag] = useState('');
  const [term, setTerm] = useState('');
  const [termSource, setTermSource] = useState<AssetTagSource>('all');
  const [collectionId, setCollectionId] = useState('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [metadataOnly, setMetadataOnly] = useState(false);
  const [sort, setSort] = useState<AssetQuery['sort']>('name');
  const [advanced, setAdvanced] = useState(false);
  const [minWidth, setMinWidth] = useState(0);
  const [minHeight, setMinHeight] = useState(0);
  const [ruleMode, setRuleMode] = useState<'all' | 'any'>('all');
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [queryName, setQueryName] = useState('');
  const [page, setPage] = useState<AssetPage>({ items: [], total: 0, nextOffset: 0 });
  const [pageOffset, setPageOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>(() => {
    try { const value: unknown = JSON.parse(saved('selected') || '[]');
      return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string' && id.length <= 80).slice(0, 100) : []; }
    catch { return []; }
  });
  const [selectionDetails, setSelectionDetails] = useState<Record<string, AssetItem>>({});
  const [detail, setDetail] = useState<AssetItem | null>(null);
  const [viewer, setViewer] = useState('');
  const [vrItems, setVrItems] = useState<AssetItem[] | null>(null);
  const [bulkEditor, setBulkEditor] = useState(false);
  const [tagBrowser, setTagBrowser] = useState(false);
  const [generationOpen, setGenerationOpen] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [compare, setCompare] = useState(false);
  const [operation, setOperation] = useState<'createFolder' | 'rename' | 'copy' | 'move' | 'recycle' | null>(null);
  const [relinkPlan, setRelinkPlan] = useState<AssetRelinkPlan | null>(null);
  const [jobId, setJobId] = useState('');
  const [job, setJob] = useState<AssetJob | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [indexPaused, setIndexPaused] = useState(false);
  const [error, setError] = useState('');
  const [backendMissing, setBackendMissing] = useState(false);
  const [notice, setNotice] = useState('');
  const [newTag, setNewTag] = useState('');
  const [newCollection, setNewCollection] = useState('');
  const [notes, setNotes] = useState('');
  const request = useRef(0);
  const rootInitialized = useRef(false);
  const selectionRestored = useRef(false);
  const selectionAnchor = useRef<string>('');
  const searchInput = useRef<HTMLInputElement>(null);
  const currentRoot = roots.find(root => root.id === rootId);
  const selectedId = selected.at(-1);
  const selectedItems = selected.map(id => page.items.find(item => item.id === id) || selectionDetails[id]).filter((item): item is AssetItem => !!item);
  const selectedImages = selectedItems.filter(item => item.isImage);
  const metadata = useMemo(() => detail?.metadata ? parseImageMetadata(detail.metadata) : null, [detail?.metadata]);

  const loadSidebar = useCallback(async () => {
    if (!api) return;
    const [rootData, collectionData, tagData, queryData, operationData] = await Promise.all([
      api.GetAssetRoots(), api.GetAssetCollections(), api.GetAssetTags(), api.GetSavedAssetQueries(), api.GetRecentAssetFileOperations()]);
    const foundRoots = JSON.parse(rootData) as AssetRoot[];
    setRoots(foundRoots);
    if (!rootInitialized.current) {
      rootInitialized.current = true;
      setRootId(current => foundRoots.some(root => root.id === current) ? current : foundRoots[0]?.id || '');
    }
    setCollections(JSON.parse(collectionData) as AssetCollection[]);
    setTags(JSON.parse(tagData) as string[]);
    setSavedQueries(JSON.parse(queryData) as SavedAssetQuery[]);
    setOperations(JSON.parse(operationData) as AssetOperation[]);
  }, [api]);

  useEffect(() => { if (active) {
    void loadSidebar().catch(reason => { setError(bridgeError(reason)); if (isMissingBridge(reason)) setBackendMissing(true); });
    void api?.IsAssetIndexPaused().then(setIndexPaused).catch(reason => { setError(bridgeError(reason)); if (isMissingBridge(reason)) setBackendMissing(true); });
  } }, [active, api, loadSidebar]);
  useEffect(() => { remember('root', rootId); remember('folder', folder); remember('view', view); }, [rootId, folder, view]);
  useEffect(() => { remember('tileSize', String(tileSize)); remember('crop', String(crop)); }, [tileSize, crop]);
  useEffect(() => { remember('expanded', String(expanded)); }, [expanded]);
  useEffect(() => { remember('splitDirection', splitDirection); remember('splitRatio', String(splitRatio)); }, [splitDirection, splitRatio]);
  useEffect(() => { remember('selected', JSON.stringify(selected)); }, [selected]);
  useEffect(() => { const timer = window.setTimeout(() => setQuerySearch(search), 180); return () => window.clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!active || !api || selectionRestored.current) return;
    selectionRestored.current = true;
    void Promise.allSettled(selected.map(id => api.GetAssetDetails(id))).then(results => {
      const details: Record<string, AssetItem> = {};
      for (const result of results) if (result.status === 'fulfilled') {
        const item = JSON.parse(result.value) as AssetItem;
        details[item.id] = item;
      }
      setSelectionDetails(details);
    });
  }, [active, api, selected]);
  useEffect(() => { setWorkspaceTabs(current => current.map(tab => tab.id === activeWorkspace ? { ...tab, rootId, folder, view } : tab)); }, [activeWorkspace, rootId, folder, view]);
  useEffect(() => { remember('secondRoot', secondRootId); remember('secondFolder', secondFolder); }, [secondRootId, secondFolder]);

  const buildQuery = useCallback((offset: number): AssetQuery => {
    const predicates: AssetRule[] = rules.filter(row => row.value.trim()).map(row => {
      const predicate: AssetRule = { mode: 'predicate', field: row.field, comparison: row.comparison, value: row.value.trim() };
      return row.negate ? { mode: 'not', children: [predicate] } : predicate;
    });
    return { rootId, folder, search: querySearch, tag, term, termSource, collectionId, favoritesOnly, metadataOnly, imagesOnly: view === 'gallery',
      includeDescendants: view === 'gallery' || !!querySearch || !!tag || !!term || !!collectionId || favoritesOnly || metadataOnly, sort, offset, limit: 100,
      minWidth, minHeight, maxWidth: 0, maxHeight: 0, rule: predicates.length ? { mode: ruleMode, children: predicates } : null };
  }, [rootId, folder, querySearch, tag, term, termSource, collectionId, favoritesOnly, metadataOnly, view, sort, minWidth, minHeight, rules, ruleMode]);

  const loadPage = useCallback(async (offset: number) => {
    if (!api || !active) return;
    const current = ++request.current;
    try {
      const result = JSON.parse(await api.QueryAssets(JSON.stringify(buildQuery(offset)))) as AssetPage;
      if (current !== request.current) return;
      setPage(result); setPageOffset(offset);
      setError('');
    } catch (reason) { if (current === request.current) setError(String(reason)); }
  }, [api, active, buildQuery]);
  useEffect(() => { setPage({ items: [], total: 0, nextOffset: 0 }); void loadPage(0); }, [loadPage, revision]);

  useEffect(() => {
    if (!api || !jobId) return;
    let disposed = false;
    const poll = async () => {
      try {
        const status = JSON.parse(await api.GetAssetJob(jobId)) as AssetJob;
        if (disposed) return;
        setJob(status);
        setRevision(value => value + 1);
        if (!['queued', 'running', 'scanning'].includes(status.state)) { setJobId(''); void loadSidebar(); }
      } catch (reason) { if (!disposed) setError(String(reason)); }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [api, jobId, loadSidebar]);

  const quickSearch = useCallback(() => {
    setRootId(''); setFolder(''); setView('explorer'); setTag(''); setTerm(''); setCollectionId(''); setFavoritesOnly(false);
    setRules([]); setSelected([]);
    window.setTimeout(() => searchInput.current?.focus(), 0);
  }, []);

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement ||
          event.target instanceof HTMLSelectElement || document.querySelector('.assets-operation-overlay')) return;
      if (event.key === 'F2' && selectedItems.length === 1) { event.preventDefault(); setOperation('rename'); }
      if (event.key === 'Delete' && selectedItems.length) { event.preventDefault(); setOperation('recycle'); }
      if (event.key === ' ' && selectedImages.length === 1) { event.preventDefault(); setViewer(selectedImages[0].id); }
      if (event.key === 'Escape') { setContextMenu(null); setSelected([]); setSelectionMode(false); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') { event.preventDefault(); searchInput.current?.focus(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); quickSearch(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') { event.preventDefault(); setSelected(page.items.map(item => item.id)); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, selectedItems, selectedImages, page.items, quickSearch]);

  useEffect(() => {
    if (!contextMenu) return;
    const dismiss = () => setContextMenu(null);
    window.addEventListener('click', dismiss);
    window.addEventListener('scroll', dismiss, true);
    return () => { window.removeEventListener('click', dismiss); window.removeEventListener('scroll', dismiss, true); };
  }, [contextMenu]);

  useEffect(() => {
    if (!api || !selectedId) { setDetail(null); return; }
    let disposed = false;
    void api.GetAssetDetails(selectedId).then(value => {
      if (disposed) return;
      const item = JSON.parse(value) as AssetItem;
      setDetail(item); setNotes(item.notes);
    }).catch(reason => { if (!disposed) setError(String(reason)); });
    return () => { disposed = true; };
  }, [api, selectedId, revision]);

  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };

  const addRoot = () => void run(async () => {
    if (!api || backendMissing) return;
    const result = await api.PickAndAddAssetRoot();
    if (!result) return;
    const added = JSON.parse(result) as { root: AssetRoot; jobId: string };
    await loadSidebar(); setRootId(added.root.id); setFolder(''); setCollectionId(''); setTag(''); setTerm(''); setJobId(added.jobId);
  });
  const relinkRoot = (id: string) => void run(async () => {
    if (!api) return;
    const result = await api.PickRelinkAssetRoot(id);
    if (result) setRelinkPlan(JSON.parse(result) as AssetRelinkPlan);
  });
  const confirmRelink = () => void run(async () => {
    if (!api || !relinkPlan) return;
    const job = await api.ConfirmAssetRootRelink(relinkPlan.id);
    setRootId(relinkPlan.rootId); setJobId(job); setRelinkPlan(null);
    await loadSidebar();
  });
  const rescan = () => void run(async () => { if (api && rootId) setJobId(await api.StartAssetIndex(rootId)); });
  const changeRoot = (id: string) => { setRootId(id); setFolder(''); setCollectionId(''); setTag(''); setTerm(''); setSelected([]); };
  const changeFolder = (path: string) => { setFolder(path); setSelected([]); };
  const toggleSelected = (item: AssetItem, multiple: boolean, range = false) => {
    setSelectionDetails(old => ({ ...old, [item.id]: item }));
    if (range) {
      const anchor = page.items.findIndex(value => value.id === selectionAnchor.current);
      const target = page.items.findIndex(value => value.id === item.id);
      if (anchor >= 0 && target >= 0) {
        const rangeItems = page.items.slice(Math.min(anchor, target), Math.max(anchor, target) + 1);
        setSelectionDetails(old => ({ ...old, ...Object.fromEntries(rangeItems.map(value => [value.id, value])) }));
        setSelected(previous => [...new Set([...previous, ...rangeItems.map(value => value.id)])].slice(0, 100));
        return;
      }
    }
    selectionAnchor.current = item.id;
    setSelected(previous => multiple ? previous.includes(item.id) ? previous.filter(id => id !== item.id) : [...previous, item.id].slice(-100) : [item.id]);
  };
  const openContextMenu = (event: React.MouseEvent, item: AssetItem) => {
    event.preventDefault();
    if (!selected.includes(item.id)) toggleSelected(item, false);
    setContextMenu({ x: Math.min(event.clientX, window.innerWidth - 190), y: Math.min(event.clientY, window.innerHeight - 230) });
  };
  const contextAction = (action: () => void) => { setContextMenu(null); action(); };
  const openItem = (item: AssetItem) => {
    if (item.isDirectory) { if (rootId !== item.rootId) setRootId(item.rootId); changeFolder(item.relativePath); return; }
    if (item.isImage) setViewer(item.id);
  };
  const edit = (favorite: boolean | null, nextNotes: string | null, addTag: string | null, removeTag: string | null) =>
    void run(async () => {
      if (!api || !detail) return;
      const updated = JSON.parse(await api.EditAsset(JSON.stringify({ id: detail.id, favorite, notes: nextNotes, addTag, removeTag }))) as AssetItem;
      setDetail(updated); setNotes(updated.notes); setNewTag('');
      setSelectionDetails(old => ({ ...old, [updated.id]: updated }));
      await loadSidebar(); setRevision(value => value + 1);
    });
  const editBatch = (changes: AssetBulkChanges) => void run(async () => {
    if (!api || !selected.length) return;
    await api.EditAssets(JSON.stringify({ ids: selected, ...changes }));
    const refreshed = await Promise.allSettled(selected.map(id => api.GetAssetDetails(id)));
    const updated: Record<string, AssetItem> = {};
    for (const result of refreshed) if (result.status === 'fulfilled') {
      const item = JSON.parse(result.value) as AssetItem;
      updated[item.id] = item;
    }
    setSelectionDetails(old => ({ ...old, ...updated }));
    setBulkEditor(false); setNotice(`${selected.length} itens atualizados.`);
    await loadSidebar(); setRevision(value => value + 1);
  });
  const makeCollection = () => void run(async () => {
    if (!api || !newCollection.trim()) return;
    const created = JSON.parse(await api.AddAssetCollection(newCollection.trim())) as AssetCollection;
    setNewCollection(''); await loadSidebar(); setCollectionId(created.id);
  });
  const switchWorkspace = (tab: WorkspaceTab) => {
    setActiveWorkspace(tab.id); setRootId(tab.rootId); setFolder(tab.folder); setView(tab.view); setSelected([]);
  };
  const addWorkspace = () => {
    if (workspaceTabs.length >= 8) return;
    const next = { id: crypto.randomUUID(), rootId, folder, view };
    setWorkspaceTabs(current => [...current, next]); setActiveWorkspace(next.id); setSelected([]);
  };
  const closeWorkspace = (id: string) => {
    if (workspaceTabs.length === 1) return;
    const remaining = workspaceTabs.filter(tab => tab.id !== id);
    setWorkspaceTabs(remaining);
    if (id === activeWorkspace) switchWorkspace(remaining[0]);
  };
  const closeMainPane = () => {
    setRootId(secondRootId || rootId); setFolder(secondFolder); setView('explorer');
    setSearch(''); setTag(''); setTerm(''); setCollectionId(''); setFavoritesOnly(false); setRules([]);
    setSelected([]); setDualPane(false);
  };
  const saveQuery = () => void run(async () => {
    if (!api || !queryName.trim()) return;
    await api.SaveAssetQuery(queryName.trim(), JSON.stringify(buildQuery(0)));
    setQueryName(''); await loadSidebar();
  });
  const undo = (id: string) => void run(async () => {
    if (!api) return;
    await api.UndoAssetFileOperation(id);
    await loadSidebar(); setRevision(value => value + 1);
    setNotice('Operação desfeita.');
  });
  const applySaved = (savedQuery: SavedAssetQuery) => {
    const query = savedQuery.query;
    setRootId(query.rootId || ''); setFolder(query.folder || ''); setSearch(query.search || '');
    setTag(query.tag || ''); setTerm(query.term || ''); setTermSource(query.termSource || 'all'); setMetadataOnly(!!query.metadataOnly);
    setCollectionId(query.collectionId || ''); setFavoritesOnly(query.favoritesOnly);
    setSort(query.sort || 'name'); setMinWidth(query.minWidth || 0); setMinHeight(query.minHeight || 0);
    setView(query.imagesOnly ? 'gallery' : 'explorer');
    const group = query.rule;
    setRuleMode(group?.mode === 'any' ? 'any' : 'all');
    setRules((group?.children || []).map(child => {
      const predicate = child.mode === 'not' ? child.children?.[0] : child;
      return { field: predicate?.field || 'metadata', comparison: predicate?.comparison || 'contains', value: predicate?.value || '', negate: child.mode === 'not' };
    }));
    setSelected([]); setAdvanced(true);
  };
  const pickTagTerm = (value: string, source: AssetTagSource) => {
    setTerm(value); setTermSource(source); setTag(''); setCollectionId(''); setFavoritesOnly(false);
    setView('gallery'); setSelected([]); setTagBrowser(false);
  };

  const parts = folder ? folder.split('/') : [];
  const imageItems = page.items.filter(item => item.isImage);
  const viewerItems = [...selectedImages, ...imageItems.filter(item => !selected.includes(item.id))];
  const vrSelection = (selectedImages.length ? selectedImages : imageItems).filter(item => item.available).slice(0, 100);
  return <div className={'tab-content assets-tab' + (expanded ? ' assets-expanded' : '')}>
    <div className="assets-heading"><div><small>BIBLIOTECA PESSOAL</small><h1>Suas artes, do seu jeito.</h1><p>Explore, compare e organize arquivos nas pastas que você escolher.</p></div>
      <button className="btn primary" onClick={addRoot} disabled={busy || !api || backendMissing}><FolderPlus size={17}/> Adicionar pasta</button></div>
    {!api && <p role="alert" className="assets-alert">A biblioteca local está disponível no aplicativo para Windows.</p>}
    {error && <p role="alert" className="assets-alert">{error}</p>}
    {notice && <p role="status" className="assets-notice">{notice}</p>}
    <nav className="assets-tabs" aria-label="Abas da biblioteca">{workspaceTabs.map((tab, index) => <div key={tab.id} className={activeWorkspace === tab.id ? 'active' : ''}>
      <button onClick={() => switchWorkspace(tab)}>{tab.view === 'gallery' ? <Images size={15}/> : <Folder size={15}/>} {roots.find(root => root.id === tab.rootId)?.path.split(/[\\/]/).at(-1) || `Acervo ${index + 1}`}</button>
      {workspaceTabs.length > 1 && <button title="Fechar aba" aria-label={`Fechar aba ${index + 1}`} onClick={() => closeWorkspace(tab.id)}><X size={13}/></button>}</div>)}
      <button className="title-btn" title="Nova aba" onClick={addWorkspace} disabled={workspaceTabs.length >= 8}><Plus size={17}/></button>
      <button className="btn secondary" onClick={() => { setDualPane(value => !value); if (!secondRootId) setSecondRootId(rootId || roots[0]?.id || ''); }} aria-pressed={dualPane}>Dois painéis</button>
      {dualPane && <div className="assets-split-controls" role="group" aria-label="Distribuição dos painéis">
        <select aria-label="Orientação dos painéis" value={splitDirection} onChange={event => setSplitDirection(event.target.value as 'columns' | 'rows')}>
          <option value="columns">Lado a lado</option><option value="rows">Um acima do outro</option>
        </select>
        <input aria-label="Tamanho do painel principal" type="range" min="25" max="75" step="5" value={splitRatio} onChange={event => setSplitRatio(Number(event.target.value))}/>
        <span>{splitRatio}%</span>
      </div>}
      <button className="btn secondary assets-expand-toggle" onClick={() => setExpanded(value => !value)} aria-pressed={expanded}>{expanded ? <Minimize2 size={15}/> : <Maximize2 size={15}/>} {expanded ? 'Mostrar cabeçalho' : 'Expandir área'}</button>
    </nav>
    <div className="assets-workspace">
      <aside className="assets-sidebar" aria-label="Navegação da biblioteca">
        <h2>Pastas <button className="title-btn" onClick={addRoot} title="Adicionar pasta" disabled={backendMissing}><Plus size={16}/></button></h2>
        {roots.length > 1 && <button className={'assets-side-item ' + (!rootId ? 'active' : '')} onClick={() => changeRoot('')}><Images size={16}/> Todos os acervos</button>}
        {roots.map(root => <div className="assets-root-row" key={root.id}><button className={'assets-side-item ' + (rootId === root.id && !collectionId && !tag && !term && !favoritesOnly ? 'active' : '')}
          title={root.path} onClick={() => changeRoot(root.id)}><Folder size={16}/><span>{root.path.split(/[\\/]/).at(-1) || root.path}</span>{!root.online && <small>offline</small>}</button>
          <button className="title-btn" title={`Relocalizar ${root.path}`} onClick={() => relinkRoot(root.id)}><RefreshCw size={13}/></button></div>)}
        <h2>Organizar</h2>
        <button className={'assets-side-item ' + (favoritesOnly ? 'active' : '')} onClick={() => { setFavoritesOnly(value => !value); setTag(''); setTerm(''); setCollectionId(''); }}><Heart size={16}/> Favoritos</button>
        {tags.slice(0, 8).map(value => <button className={'assets-side-item ' + (tag === value ? 'active' : '')} key={value}
          onClick={() => { setTag(tag === value ? '' : value); setTerm(''); setFavoritesOnly(false); setCollectionId(''); }}><Tag size={15}/>{value}</button>)}
        <button className={'assets-side-item ' + (term ? 'active' : '')} onClick={() => setTagBrowser(true)}><Tag size={15}/> Todas as tags</button>
        <h2>Coleções</h2>
        {collections.map(value => <button className={'assets-side-item ' + (collectionId === value.id ? 'active' : '')} key={value.id}
          onClick={() => { setCollectionId(collectionId === value.id ? '' : value.id); setFavoritesOnly(false); setTag(''); setTerm(''); }}><Images size={16}/>{value.name}</button>)}
        <div className="assets-create"><input aria-label="Nova coleção" placeholder="Nova coleção" maxLength={90} value={newCollection} onChange={event => setNewCollection(event.target.value)}
          onKeyDown={event => { if (event.key === 'Enter') makeCollection(); }}/><button className="title-btn" disabled={!newCollection.trim() || busy} onClick={makeCollection} title="Criar coleção"><Plus size={17}/></button></div>
        <h2>Buscas salvas</h2>{savedQueries.map(value => <button className="assets-side-item" key={value.id} onClick={() => applySaved(value)}><Search size={15}/>{value.name}</button>)}
        <button className="assets-side-item" onClick={() => void run(async () => { if (!api) return; const path = await api.BackupAssetLibrary(); if (path) setNotice('Backup salvo em ' + path); })}><Download size={15}/> Backup do catálogo</button>
        {operations.length > 0 && <details className="assets-history"><summary>Histórico de arquivos</summary>{operations.slice(0, 12).map(value => <div key={value.id}>
          <span title={value.destinationRelativePath || value.sourceRelativePath}>{value.kind} · {value.destinationRelativePath || value.sourceRelativePath}</span>
          <small>{value.state}{value.error && `: ${value.error}`}</small>
          {value.state === 'completed' && ['rename', 'move'].includes(value.kind) && <button onClick={() => undo(value.id)} disabled={busy}>Desfazer</button>}
        </div>)}</details>}
      </aside>
      <div className={'assets-panes' + (dualPane ? splitDirection === 'rows' ? ' is-stacked' : ' is-split' : '')}
        style={dualPane ? splitDirection === 'rows'
          ? { gridTemplateRows: `minmax(0,${splitRatio}fr) minmax(0,${100 - splitRatio}fr)` }
          : { gridTemplateColumns: `minmax(0,${splitRatio}fr) minmax(0,${100 - splitRatio}fr)` } : undefined}><main className="assets-main">
        <div className="assets-toolbar">
          <div className="assets-views" role="group" aria-label="Modo de visualização">
            <button className={'btn ' + (view === 'gallery' ? 'primary' : 'secondary')} aria-pressed={view === 'gallery'} onClick={() => setView('gallery')}><Grid2X2 size={17}/> Galeria</button>
            <button className={'btn ' + (view === 'explorer' ? 'primary' : 'secondary')} aria-pressed={view === 'explorer'} onClick={() => setView('explorer')}><List size={17}/> Explorador</button>
          </div>
          <label className="assets-search"><Search size={17}/><input ref={searchInput} value={search} maxLength={200} onChange={event => setSearch(event.target.value)} placeholder="Buscar por nome, nota ou metadado" aria-label="Buscar arquivos"/></label>
          <button className="btn secondary" onClick={quickSearch} title="Buscar em todas as pastas cadastradas (Ctrl+K)"><Search size={15}/> Busca rápida</button>
          <select aria-label="Ordenar" value={sort} onChange={event => setSort(event.target.value as AssetQuery['sort'])}><option value="name">Nome</option><option value="date">Mais recentes</option><option value="size">Tamanho</option><option value="type">Tipo</option></select>
          <button className="title-btn" onClick={rescan} disabled={!rootId || busy} title="Atualizar índice"><RefreshCw size={17}/></button>
          <button className="btn secondary" onClick={() => void run(async () => { await api?.SetAssetIndexPaused(!indexPaused); setIndexPaused(!indexPaused); })}>{indexPaused ? 'Retomar índice' : 'Pausar índice'}</button>
          <button className="btn secondary" onClick={() => setAdvanced(value => !value)} aria-expanded={advanced}>Filtros</button>
          <button className="btn secondary" onClick={() => setTagBrowser(true)}><Tag size={15}/> Todas as tags</button>
          <button className="btn secondary" disabled={!api || backendMissing}
            onClick={() => setVrItems(vrSelection)}>Abrir no VR</button>
          <button className={'btn ' + (metadataOnly ? 'primary' : 'secondary')} aria-pressed={metadataOnly}
            onClick={() => { setMetadataOnly(value => !value); setView('gallery'); setSelected([]); }}>
            <Images size={15}/> Com metadados
          </button>
          {view === 'gallery' && <><label className="assets-tile-size">Miniaturas <input type="range" min="120" max="260" step="10" value={tileSize} onChange={event => setTileSize(Number(event.target.value))}/></label>
            <button className="btn secondary" aria-pressed={crop} onClick={() => setCrop(value => !value)}>{crop ? 'Recortar' : 'Encaixar'}</button></>}
        </div>
        {term && <div className="assets-term-filter" role="status"><Tag size={15}/> {term} · {termSource === 'all' ? 'todas as origens' : termSource === 'manual' ? 'manual' : termSource === 'positive' ? 'prompt positivo' : 'prompt negativo'}
          <button onClick={() => setTerm('')} aria-label="Limpar filtro de tag"><X size={15}/></button></div>}
        {advanced && <section className="assets-advanced" aria-label="Filtros avançados">
          <label>Largura mínima <input type="number" min="0" max="100000" value={minWidth} onChange={event => setMinWidth(Math.max(0, Number(event.target.value) || 0))}/></label>
          <label>Altura mínima <input type="number" min="0" max="100000" value={minHeight} onChange={event => setMinHeight(Math.max(0, Number(event.target.value) || 0))}/></label>
          <label>Combinar regras <select value={ruleMode} onChange={event => setRuleMode(event.target.value as 'all' | 'any')}><option value="all">Todas</option><option value="any">Qualquer uma</option></select></label>
          {rules.map((row, index) => <div className="assets-rule" key={index}>
            <select aria-label={`Campo da regra ${index + 1}`} value={row.field} onChange={event => setRules(old => old.map((value, i) => i === index ? { ...value, field: event.target.value, comparison: ['name','notes','metadata'].includes(event.target.value) ? 'contains' : event.target.value === 'tag' ? 'eq' : 'gte' } : value))}>
              <option value="metadata">Metadados</option><option value="name">Nome</option><option value="notes">Notas</option><option value="tag">Tag</option><option value="width">Largura</option><option value="height">Altura</option><option value="ratio">Proporção</option><option value="size">Tamanho em bytes</option>
            </select>
            <select aria-label={`Comparação da regra ${index + 1}`} value={row.comparison} onChange={event => setRules(old => old.map((value, i) => i === index ? { ...value, comparison: event.target.value } : value))}>
              <option value="contains">Contém</option><option value="eq">Igual</option><option value="gte">Pelo menos</option><option value="lte">No máximo</option>
            </select>
            <input aria-label={`Valor da regra ${index + 1}`} value={row.value} maxLength={200} onChange={event => setRules(old => old.map((value, i) => i === index ? { ...value, value: event.target.value } : value))}/>
            <label><input type="checkbox" checked={row.negate} onChange={event => setRules(old => old.map((value, i) => i === index ? { ...value, negate: event.target.checked } : value))}/> Não</label>
            <button className="title-btn" title="Remover regra" onClick={() => setRules(old => old.filter((_, i) => i !== index))}><X size={15}/></button>
          </div>)}
          <div className="assets-advanced-actions"><button className="btn secondary" disabled={rules.length >= 12} onClick={() => setRules(old => [...old, newRule()])}><Plus size={15}/> Regra</button>
            <input aria-label="Nome da busca" maxLength={90} placeholder="Nome da busca" value={queryName} onChange={event => setQueryName(event.target.value)}/>
            <button className="btn secondary" disabled={!queryName.trim() || busy} onClick={saveQuery}>Salvar busca</button></div>
        </section>}
        <div className="assets-file-toolbar" role="group" aria-label="Organizar arquivos">
          {dualPane && <button className="btn secondary" onClick={closeMainPane} title="Fechar painel principal e manter o segundo"><X size={15}/> Fechar este painel</button>}
          <button className={'btn ' + (selectionMode ? 'primary' : 'secondary')} aria-pressed={selectionMode} onClick={() => { setSelectionMode(value => !value); setContextMenu(null); }}><List size={15}/> Selecionar vários</button>
          <button className="btn secondary" disabled={!page.items.length} onClick={() => { setSelected(page.items.map(item => item.id)); setSelectionDetails(old => ({ ...old, ...Object.fromEntries(page.items.map(item => [item.id, item])) })); setSelectionMode(true); }}>Selecionar página</button>
          {selected.length > 0 && <button className="btn secondary" onClick={() => { setSelected([]); setContextMenu(null); }}>Limpar seleção</button>}
          <button className="btn secondary" disabled={selectedItems.length < 2} onClick={() => setBulkEditor(true)}><Tag size={15}/> Editar {selectedItems.length || ''} itens</button>
          <button className="btn secondary" disabled={!rootId} onClick={() => setOperation('createFolder')}><FolderPlus size={15}/> Pasta</button>
          <button className="btn secondary" disabled={!selectedItems.length} onClick={() => setOperation('rename')}><Pencil size={15}/> Renomear</button>
          <button className="btn secondary" disabled={!selectedItems.length} onClick={() => setOperation('copy')}><Copy size={15}/> Copiar</button>
          <button className="btn secondary" disabled={!selectedItems.length} onClick={() => setOperation('move')}><ArrowRight size={15}/> Mover</button>
          <button className="btn secondary" disabled={!selectedItems.length} onClick={() => setOperation('recycle')}><Trash2 size={15}/> Lixeira</button>
        </div>
        <nav className="assets-breadcrumb" aria-label="Caminho da pasta">
          <button onClick={() => changeFolder('')} disabled={!rootId}>{currentRoot?.path.split(/[\\/]/).at(-1) || 'Todas as pastas'}</button>
          {parts.map((part, index) => <span key={index}> / <button onClick={() => changeFolder(parts.slice(0, index + 1).join('/'))}>{part}</button></span>)}
          {folder && <button className="title-btn" title="Pasta anterior" onClick={() => changeFolder(parts.slice(0, -1).join('/'))}><ArrowLeft size={16}/></button>}
          {!folder && <ArrowRight size={14} className="assets-quiet"/>}
        </nav>
        {job && ['queued', 'running', 'scanning'].includes(job.state) && <p className="assets-progress" role="status">{job.state === 'scanning' ? 'Atualizando catálogo' : job.rootId ? 'Indexando' : 'Processando'} {job.seen} itens… {job.rootId && <button onClick={() => api?.CancelAssetIndex(job.id)}>Cancelar</button>}</p>}
        {indexPaused && <p className="assets-progress" role="status">Indexação pausada para liberar recursos do computador.</p>}
        {job && job.state === 'partial' && <p className="assets-progress" role="alert">Alguns arquivos não puderam ser lidos. O restante do catálogo foi preservado.</p>}
        {job && job.state === 'failed' && <p className="assets-progress" role="alert">Operação falhou: {job.error}</p>}
        {!roots.length && <div className="assets-empty"><Images size={36}/><h2>Comece pelo seu acervo</h2><p>Escolha uma pasta de artes. Os arquivos continuam onde já estão.</p><button className="btn primary" onClick={addRoot} disabled={backendMissing}>Escolher pasta</button></div>}
        {roots.length > 0 && page.items.length === 0 && <div className="assets-empty"><p>Nenhum item encontrado neste filtro.</p></div>}
        {view === 'gallery' ? <div className="assets-grid" aria-label="Galeria de artes" style={{ gridTemplateColumns: `repeat(auto-fill,minmax(${tileSize}px,1fr))` }}>{page.items.map(item => <button key={item.id}
          className={'assets-card ' + (selected.includes(item.id) ? 'selected' : '')} aria-pressed={selected.includes(item.id)}
          onClick={event => toggleSelected(item, selectionMode || event.ctrlKey || event.metaKey, event.shiftKey)} onDoubleClick={() => { if (!selectionMode) openItem(item); }} onContextMenu={event => openContextMenu(event, item)}>
          <div className={'assets-card-image ' + (crop ? 'crop' : '')} style={{ height: Math.round(tileSize * .84) }}><img loading="lazy" src={mediaUrl(item, 'thumb')} alt=""/></div>
          <span className="assets-card-name" title={item.name}>{item.name}</span>
          {item.hasMetadata && <span className="assets-card-metadata" aria-hidden="true" title="Metadados indexados">META</span>}
          <small>{item.favorite ? '♥ ' : ''}{item.tags.slice(0, 2).join(' · ')}</small>
        </button>)}</div> : <div className="assets-list" role="list" aria-label="Arquivos da pasta">
          {page.items.map(item => <button role="listitem" key={item.id} className={'assets-row ' + (selected.includes(item.id) ? 'selected' : '')}
            aria-selected={selected.includes(item.id)} onClick={event => toggleSelected(item, selectionMode || event.ctrlKey || event.metaKey, event.shiftKey)} onDoubleClick={() => { if (!selectionMode) openItem(item); }} onContextMenu={event => openContextMenu(event, item)}>
            {item.isImage ? <img src={mediaUrl(item, 'thumb')} alt="" loading="lazy"/> : <span className="assets-file-icon"><Folder size={19}/></span>}
            <span className="assets-row-name" title={item.relativePath}>{item.name}{item.hasMetadata && <span className="assets-row-metadata" aria-hidden="true" title="Metadados indexados">META</span>}{!rootId && <small>{roots.find(value => value.id === item.rootId)?.path} / {item.relativePath}</small>}</span><span>{item.isDirectory ? 'Pasta' : readableSize(item.size)}</span><span>{new Date(item.modifiedUtc).toLocaleDateString('pt-BR')}</span>
          </button>)}</div>}
        {page.total > page.items.length && <div className="assets-pagination">
          <button className="btn secondary" disabled={pageOffset === 0} onClick={() => { setSelected([]); void loadPage(Math.max(0, pageOffset - 100)); }}>Anterior</button>
          <span>{pageOffset + 1}–{Math.min(page.nextOffset, page.total)} de {page.total}</span>
          <button className="btn secondary" disabled={page.nextOffset >= page.total} onClick={() => { setSelected([]); void loadPage(page.nextOffset); }}>Próxima</button>
        </div>}
        <footer className="assets-footer"><span>{page.total} itens · {selected.length} selecionado(s)</span>
          <div>{selected.length > 1 && <button className="btn secondary" onClick={() => setBulkEditor(true)}><Pencil size={15}/> Editar seleção</button>}
            {selectedImages.length >= 2 && selectedImages.length <= 4 && <button className="btn secondary" onClick={() => setCompare(true)}>Comparar {selectedImages.length}</button>}
            {selectedImages.length === 1 && <button className="btn secondary" onClick={() => setViewer(selectedImages[0].id)}>Visualizar</button>}</div></footer>
      </main>
      {dualPane && <AssetSecondaryPane roots={roots} rootId={secondRootId || rootId || roots[0]?.id || ''} folder={secondFolder}
        onRoot={setSecondRootId} onFolder={setSecondFolder} selectedCount={selectedItems.length}
        onCopy={() => { setOperationTarget(true); setOperation('copy'); }} onMove={() => { setOperationTarget(true); setOperation('move'); }}
        onClose={() => setDualPane(false)}/>}</div>
      <aside className="assets-inspector" aria-label="Detalhes do item selecionado">
        <h2>Detalhes</h2>
        {!detail ? <p>Selecione uma arte ou arquivo para ver informações.</p> : <>
          {detail.isImage && <img className="assets-inspector-image" src={mediaUrl(detail, 'thumb')} alt={detail.name}/>}
          <strong title={detail.name}>{detail.name}</strong><small>{detail.relativePath}</small>
          <p>{detail.isDirectory ? 'Pasta' : readableSize(detail.size)} · {new Date(detail.modifiedUtc).toLocaleString('pt-BR')}</p>
          {detail.width > 0 && <p>{detail.width} × {detail.height} pixels</p>}
          <button className="btn secondary" onClick={() => edit(!detail.favorite, null, null, null)} disabled={busy}><Heart size={17} fill={detail.favorite ? 'currentColor' : 'none'}/>{detail.favorite ? 'Favorito' : 'Favoritar'}</button>
          <h3>Tags</h3><div className="assets-tags">{detail.tags.map(value => <button key={value} onClick={() => edit(null, null, null, value)} title={`Remover ${value}`}>{value} <X size={13}/></button>)}</div>
          <div className="assets-create"><input aria-label="Nova tag" placeholder="Adicionar tag" maxLength={80} value={newTag} onChange={event => setNewTag(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && newTag.trim()) edit(null, null, newTag, null); }}/><button className="title-btn" title="Adicionar tag" disabled={!newTag.trim() || busy} onClick={() => edit(null, null, newTag, null)}><Plus size={17}/></button></div>
          <h3>Coleções</h3>{collections.map(value => <button key={value.id} className="assets-collection-add" onClick={() => void run(async () => { await api?.SetAssetCollectionItem(value.id, detail.id, true); setRevision(old => old + 1); })}>+ {value.name}</button>)}
          <h3>Notas</h3><textarea aria-label="Notas" maxLength={8000} value={notes} onChange={event => setNotes(event.target.value)}/><button className="btn secondary" disabled={busy || notes === detail.notes} onClick={() => edit(null, notes, null, null)}>Salvar nota</button>
          {metadata && <><h3>Dados da imagem · {metadata.source}</h3>
            <button className="btn secondary" onClick={() => setGenerationOpen(true)}>Ver geração e nodes</button><div className="assets-metadata">
            {metadata.summary.length > 0 && <><p>Parâmetros ComfyUI registrados no arquivo (editáveis, não comprovam a origem):</p>
              <dl className="assets-metadata-summary">{metadata.summary.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></>}
          </div></>}
        </>}
      </aside>
    </div>
    {viewer && <AssetViewer items={viewerItems} initialId={viewer} onClose={() => setViewer('')}/>}
    {vrItems && <AssetVrPanel items={vrItems} query={buildQuery(0)} view={view} onClose={() => setVrItems(null)}/>}
    {generationOpen && detail?.metadata && <AssetGenerationModal key={detail.id} name={detail.name} metadata={detail.metadata} onClose={() => setGenerationOpen(false)}/>}
    {tagBrowser && <AssetTagBrowser onClose={() => setTagBrowser(false)} onPick={pickTagTerm}/>}
    {contextMenu && <div className="assets-context-menu" role="menu" aria-label="Ações da seleção" style={{ left: contextMenu.x, top: contextMenu.y }} onClick={event => event.stopPropagation()}>
      <span>{selected.length} selecionado(s)</span>
      <button role="menuitem" disabled={selectedItems.length < 2} onClick={() => contextAction(() => setBulkEditor(true))}><Tag size={15}/> Editar tags, favoritos e coleções</button>
      <button role="menuitem" disabled={!selectedItems.length} onClick={() => contextAction(() => setOperation('copy'))}><Copy size={15}/> Copiar</button>
      <button role="menuitem" disabled={!selectedItems.length} onClick={() => contextAction(() => setOperation('move'))}><ArrowRight size={15}/> Mover</button>
      <button role="menuitem" disabled={!selectedItems.length} onClick={() => contextAction(() => setOperation('rename'))}><Pencil size={15}/> Renomear</button>
      <button role="menuitem" disabled={!selectedItems.length} onClick={() => contextAction(() => setOperation('recycle'))}><Trash2 size={15}/> Enviar à Lixeira</button>
    </div>}
    {bulkEditor && <AssetBulkEditor items={selectedItems} collections={collections} busy={busy} onClose={() => setBulkEditor(false)} onApply={editBatch}/>}
    {compare && <AssetCompare items={selectedImages} onClose={() => setCompare(false)}/>}
    {operation && <AssetFileActions key={operation} type={operation} items={selectedItems} roots={roots} rootId={rootId || roots[0]?.id || ''} folder={folder}
      targetRootId={operationTarget ? (secondRootId || rootId) : undefined} targetFolder={operationTarget ? secondFolder : undefined}
      onClose={() => { setOperation(null); setOperationTarget(false); }} onStarted={id => { setJobId(id); setSelected([]); }}/>}
    {relinkPlan && <div className="assets-operation-overlay" role="presentation"><section className="assets-operation" role="dialog" aria-modal="true" aria-label="Relocalizar pasta">
      <header><h2>Relocalizar pasta</h2><button className="title-btn" onClick={() => setRelinkPlan(null)} aria-label="Fechar"><X size={18}/></button></header>
      <p>Atual: {relinkPlan.oldPath}</p><p>Nova: {relinkPlan.newPath}</p>
      <p>{relinkPlan.matched} caminhos correspondem; {relinkPlan.missing} não foram encontrados. As anotações desses itens permanecem no catálogo.</p>
      <div className="assets-operation-buttons"><button className="btn secondary" onClick={() => setRelinkPlan(null)}>Cancelar</button>
        <button className="btn primary" disabled={busy} onClick={confirmRelink}>Confirmar localização</button></div>
    </section></div>}
  </div>;
}
