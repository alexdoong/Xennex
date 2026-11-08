import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Palette, X, Undo2, Redo2, Minus, FolderOpen, ArrowUp, ArrowDown } from 'lucide-react';
import type { SkinConfig } from '../../webview';
import { normalizeSkinConfig, skinColor, skinColorHex } from '../../utils/skinUtils';
import { DEFAULT_SKIN } from './skinDefaults';
import { SKIN_FIELDS, SKIN_PALETTES, SKIN_PRESETS, type SkinField } from './skinFields';
import { CUSTOMIZABLE_TABS } from '../../layout/navigation';
const SETTINGS_SECTIONS = [
  { id:'behavior', title:'Comportamento' }, { id:'layout', title:'Interface e layout' },
  { id:'skins', title:'Skins' }, { id:'about', title:'Sobre e atualizações' }
];

interface Props {
  skinName: string;
  compact?: boolean;
  onClose: () => void;
  onSaved: (config: SkinConfig) => void;
  onPreview: (config: SkinConfig | null) => void;
}
export default function SkinEditorModal({ skinName, compact = false, onClose, onSaved, onPreview }: Props) {
  const [history, setHistory] = useState<{ past: SkinConfig[]; current: SkinConfig; future: SkinConfig[] }>({ past: [], current: DEFAULT_SKIN, future: [] });
  const [baseline, setBaseline] = useState('');
  const [section, setSection] = useState('Fundo');
  const [search, setSearch] = useState('');
  const [minimized, setMinimized] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [copyName, setCopyName] = useState('');
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState('');
  const [ready, setReady] = useState(false);
  const alive = useRef(true);
  const config = history.current;
  const dirty = ready && JSON.stringify(config) !== baseline;
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (!api) throw new Error('Abra o editor dentro do Xennex.');
        const cfg = normalizeSkinConfig(JSON.parse(await api.GetSkinConfig(skinName)));
        if (cancelled) return;
        setHistory({ past: [], current: cfg, future: [] }); setBaseline(JSON.stringify(cfg)); setReady(true);
        setCopyName(cfg.name === 'default' ? 'Minha skin' : cfg.name + ' cópia');
      } catch (error) { if (!cancelled) setMessage(String(error)); }
      finally { if (!cancelled) setBusy(false); }
    })();
    return () => { cancelled = true; };
  }, [api, skinName]);
  useEffect(() => { if (ready) onPreview(normalizeSkinConfig(config)); }, [config, ready, onPreview]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; onPreview(null); }; }, [onPreview]);
  const change = (patch: Partial<SkinConfig>) => {
    setConfirmClose(false);
    setHistory(old => ({ past: [...old.past.slice(-49), old.current], current: { ...old.current, ...patch }, future: [] }));
  };
  const undo = () => setHistory(old => old.past.length ? ({ past: old.past.slice(0,-1), current: old.past[old.past.length-1], future: [old.current,...old.future] }) : old);
  const redo = () => setHistory(old => old.future.length ? ({ past:[...old.past,old.current],current:old.future[0],future:old.future.slice(1) }) : old);
  const moveNavigation = (id: string, direction: -1 | 1) => {
    const order = [...config.navigationOrder];
    const index = order.indexOf(id), target = index + direction;
    if (index < 0 || target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    change({ navigationOrder: order });
  };
  const moveSettingsSection = (id: string, direction: -1 | 1) => {
    const order = [...config.settingsSectionOrder];
    const index = order.indexOf(id), target = index + direction;
    if (index < 0 || target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    change({ settingsSectionOrder: order });
  };
  const save = async (asCopy: boolean, closeAfter = false) => {
    if (!api || busy) return;
    setBusy(true); setMessage('');
    try {
      let next = normalizeSkinConfig(config);
      if (asCopy || config.name.toLowerCase() === 'default') {
        if (!copyName.trim()) throw new Error('Informe o nome da cópia.');
        next = normalizeSkinConfig(JSON.parse(await api.SaveSkinAs(copyName.trim(), config.name, JSON.stringify(next))));
      } else if (!await api.SaveSkinConfig(config.name, JSON.stringify(next))) throw new Error('Não foi possível salvar.');
      if (!alive.current) return;
      setHistory({ past: [], current: next, future: [] }); setBaseline(JSON.stringify(next));
      setCopyName(next.name + ' cópia'); setConfirmClose(false); setMessage('Skin salva e aplicada.');
      onSaved(next);
      if (closeAfter) onClose();
    } catch (error) { if (alive.current) setMessage(String(error)); }
    finally { if (alive.current) setBusy(false); }
  };
  const importAsset = async (field: SkinField) => {
    if (!api) return;
    if (config.name.toLowerCase() === 'default') { setMessage('Salve uma cópia pessoal antes de importar arquivos do computador.'); return; }
    setBusy(true);
    try {
      const url = await api.PickAndImportAsset(config.name, field.key === 'backgroundUrl' && config.backgroundType === 'video' ? 'video' : 'image');
      if (url && alive.current) change({ [field.key]: url });
    } catch (error) { if (alive.current) setMessage(String(error)); }
    finally { if (alive.current) setBusy(false); }
  };
  const requestClose = () => { if (dirty) { setConfirmClose(true); setMinimized(false); } else onClose(); };
  const fields = SKIN_FIELDS.filter(f => search ? f.label.toLocaleLowerCase().includes(search.toLocaleLowerCase()) : f.section === section);
  const renderField = (field: SkinField) => {
    const id = 'skin-' + field.key, value = config[field.key];
    return <div className="skin-dock-field" key={field.key}>
      <label htmlFor={id}>{field.label}</label>
      {field.kind === 'range' && <div className="skin-range-row">
        <input id={id} type="range" min={field.min} max={field.max} step={field.step} value={Number(value)} onChange={e => change({ [field.key]: Number(e.target.value) })} />
        <input aria-label={field.label + ' valor'} type="number" min={field.min} max={field.max} step={field.step} value={Number(value)} onChange={e => { if (e.target.value !== '') change({ [field.key]: Math.max(field.min!, Math.min(field.max!, Number(e.target.value))) }); }} />
      </div>}
      {field.kind === 'color' && <div className="skin-color-row">
        <span className="skin-color-swatch" style={{ background: skinColor(String(value)) }} />
        <input id={id} value={String(value)} maxLength={128} onChange={e => change({ [field.key]: e.target.value })} aria-invalid={!CSS.supports('color',String(value))} />
        <input type="color" aria-label={'Escolher ' + field.label} value={skinColorHex(String(value))} onChange={e => change({ [field.key]: e.target.value })} />
      </div>}
      {field.kind === 'select' && <select id={id} value={String(value)} onChange={e => change({ [field.key]: typeof value === 'number' ? Number(e.target.value) : e.target.value })}>{field.options?.map(([v,label]) => <option value={v} key={v}>{label}</option>)}</select>}
      {field.kind === 'check' && <input id={id} type="checkbox" checked={Boolean(value)} onChange={e => change({ [field.key]: e.target.checked })} />}
      {field.kind === 'asset' && <div className="skin-asset-row">
        <input id={id} value={String(value)} maxLength={4096} placeholder="https://… ou importe do PC" onChange={e => change({ [field.key]: e.target.value })} />
        <button type="button" className="btn secondary" title={'Importar ' + field.label} onClick={() => void importAsset(field)}><FolderOpen size={16}/></button>
        <button type="button" className="btn secondary" title={'Limpar ' + field.label} onClick={() => change({ [field.key]: '' })}><X size={16}/></button>
      </div>}
    </div>;
  };
  return createPortal(minimized ? <button className={`skin-dock-reopen ${compact ? 'skin-dock-compact' : ''}`} onClick={() => setMinimized(false)}><Palette size={18}/> Editar skin {dirty ? '•' : ''}</button> :
    <aside className={`skin-dock ${compact ? 'skin-dock-compact' : ''}`} aria-label="Editor de skins" onKeyDown={e => { if (e.key === 'Escape' && !busy) requestClose(); }}>
      <header><div><strong>Seu espaço, seu estilo</strong><small>{ready ? config.name : 'Carregando…'}{dirty ? ' • alterações não salvas' : ''}</small></div>
        <button className="btn secondary" title="Recolher editor" onClick={() => setMinimized(true)}><Minus size={18}/></button>
        <button className="btn secondary" title="Fechar editor" disabled={busy} onClick={requestClose}><X size={18}/></button>
      </header>
      <p className="skin-dock-hint">Prévia ao vivo. Navegue pelas abas ou recolha o painel para conferir o resultado.</p>
      <div className="skin-dock-tools">
        <button className="btn secondary" title="Desfazer" disabled={busy || !history.past.length} onClick={undo}><Undo2 size={16}/></button>
        <button className="btn secondary" title="Refazer" disabled={busy || !history.future.length} onClick={redo}><Redo2 size={16}/></button>
        <button className="btn secondary" disabled={busy || !ready} onClick={() => change({ ...DEFAULT_SKIN, name:config.name })}>Restaurar visual</button>
      </div>
      <input className="skin-search" aria-label="Buscar ajuste" placeholder="Buscar ajuste…" value={search} onChange={e => setSearch(e.target.value)}/>
      <nav aria-label="Seções da skin">{['Fundo','Cores','Painéis','Cartões','Barras','Layout','Estrutura'].map(tab => <button key={tab} className={tab === section && !search ? 'selected' : ''} onClick={() => { setSection(tab); setSearch(''); }}>{tab}</button>)}</nav>
      <div className="skin-dock-body"><fieldset disabled={busy || !ready}>
        {(section === 'Estrutura' && !search) && <div className="skin-layout-presets" role="group" aria-label="Estilos prontos">{SKIN_PRESETS.map(preset => <button type="button" key={preset.name}
          onClick={() => change(preset.patch)}><span style={{ background:preset.patch.panelColor, borderColor:preset.patch.primaryColor }}/><strong>{preset.name}</strong><small>{preset.description}</small></button>)}</div>}
        {(section === 'Cores' && !search) && <div className="skin-palettes">{SKIN_PALETTES.map(({name,...palette}) => <button type="button" key={name} onClick={() => change({ ...palette, sidebarColor:palette.panelColor,titlebarColor:palette.panelColor,borderColor:palette.secondaryTextColor })}><span style={{background:palette.primaryColor}}/>{name}</button>)}</div>}
        {fields.map(renderField)}
        {(section === 'Estrutura' && !search) && <div className="skin-navigation-order"><h3>Ordem dos atalhos</h3><p>Configurações permanece acessível no fim da navegação.</p>
          {config.navigationOrder.map((id, index) => { const tab = CUSTOMIZABLE_TABS.find(value => value.id === id); if (!tab) return null;
            return <div key={id}><span>{tab.title}</span><button type="button" title={`Subir ${tab.title}`} disabled={index === 0} onClick={() => moveNavigation(id,-1)}><ArrowUp size={15}/></button>
              <button type="button" title={`Descer ${tab.title}`} disabled={index === config.navigationOrder.length - 1} onClick={() => moveNavigation(id,1)}><ArrowDown size={15}/></button></div>; })}</div>}
        {(section === 'Estrutura' && !search) && <div className="skin-navigation-order"><h3>Blocos de Configurações</h3><p>Altere a ordem destes cartões; a opção de colunas está acima.</p>
          {config.settingsSectionOrder.map((id, index) => { const block = SETTINGS_SECTIONS.find(value => value.id === id); if (!block) return null;
            return <div key={id}><span>{block.title}</span><button type="button" title={`Subir bloco ${block.title}`} disabled={index === 0} onClick={() => moveSettingsSection(id,-1)}><ArrowUp size={15}/></button>
              <button type="button" title={`Descer bloco ${block.title}`} disabled={index === config.settingsSectionOrder.length - 1} onClick={() => moveSettingsSection(id,1)}><ArrowDown size={15}/></button></div>; })}</div>}
        {!fields.length && section !== 'Estrutura' && <p>Nenhum ajuste encontrado.</p>}
      </fieldset></div>
      <footer>
        {message && <p role="status">{message}</p>}
        {confirmClose ? <div className="skin-close-check"><p>Salvar as alterações antes de fechar?</p><div>
          <button className="btn secondary" onClick={() => setConfirmClose(false)}>Continuar</button>
          <button className="btn secondary" disabled={busy} onClick={onClose}>Descartar</button>
          <button className="btn primary" disabled={busy} onClick={() => void save(false,true)}>Salvar e fechar</button>
        </div></div> : null}
        <label htmlFor="skin-copy-name">{config.name === 'default' ? 'Salvar como skin pessoal' : 'Nome para salvar uma cópia'}</label>
        <input id="skin-copy-name" value={copyName} maxLength={80} disabled={busy} onChange={e => setCopyName(e.target.value)}/>
        <div className="skin-save-row">
          {config.name !== 'default' && <button className="btn secondary" disabled={busy || !ready} onClick={() => void save(true)}>Salvar cópia</button>}
          <button className="btn primary" disabled={busy || !ready} onClick={() => void save(false)}>{busy ? 'Aguarde…' : config.name === 'default' ? 'Criar e aplicar cópia' : 'Salvar e aplicar'}</button>
        </div>
      </footer>
    </aside>, document.body);
}
