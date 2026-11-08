import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, GripVertical } from 'lucide-react';
import { mediaUrl, type AssetFileChoice, type AssetItem, type AssetNamingRule } from './types';

type Props = {
  items: AssetItem[]; enabled: boolean; rule: AssetNamingRule; choices: Record<string, AssetFileChoice>;
  conflicts: string[]; busy: boolean; onEnabled: (value: boolean) => void;
  onRule: (value: AssetNamingRule) => void; onOrder: (value: AssetItem[]) => void;
  onChoice: (id: string, value: AssetFileChoice | null) => void;
};

export default function AssetNamingEditor({ items, enabled, rule, choices, conflicts, busy, onEnabled, onRule, onOrder, onChoice }: Props) {
  const [sort, setSort] = useState('selection');
  const [expanded, setExpanded] = useState(enabled);
  const [dragged, setDragged] = useState('');
  const [initial] = useState(items);
  useEffect(() => { if (conflicts.length) setExpanded(true); }, [conflicts]);
  const move = (from: number, to: number) => {
    if (busy || from === to || from < 0 || to < 0 || to >= items.length) return;
    const next = [...items]; next.splice(to, 0, next.splice(from, 1)[0]);
    setSort('manual'); onOrder(next);
  };
  const orderBy = (value: string) => {
    setSort(value);
    if (value === 'manual') return;
    const collator = new Intl.Collator('pt-BR', { numeric: true, sensitivity: 'base' });
    const next = value === 'selection' ? [...initial] : [...items].sort((a, b) => value === 'name'
      ? collator.compare(a.name, b.name) : (value === 'newest' ? b.modifiedUtc - a.modifiedUtc : a.modifiedUtc - b.modifiedUtc)
        || collator.compare(a.name, b.name));
    onOrder(next);
  };
  const canNumber = items.every(item => !item.isDirectory);
  return <fieldset className="assets-naming-editor" disabled={busy}>
    <label className="assets-naming-toggle"><input type="checkbox" checked={enabled} disabled={!canNumber}
      onChange={event => { onEnabled(event.target.checked); if (event.target.checked) setExpanded(true); }}/>
      Usar padrão de numeração</label>
    {!canNumber && <p>A numeração é para arquivos. Selecione as pastas separadamente.</p>}
    {enabled && <>
      <div className="assets-naming-fields">
        <label>Nome base<input value={rule.baseName} maxLength={100} onChange={event => onRule({ ...rule, baseName: event.target.value })} placeholder="denia"/></label>
        <label>Padrão<input value={rule.pattern} maxLength={120} onChange={event => onRule({ ...rule, pattern: event.target.value })}/></label>
        <label>Aplicar a<select value={rule.scope} onChange={event => onRule({ ...rule, scope: event.target.value as AssetNamingRule['scope'] })}>
          <option value="all">Todos os arquivos</option><option value="conflicts">Somente nomes em conflito</option></select></label>
        <label>Dígitos<input type="number" min="1" max="9" value={rule.digits} onChange={event => onRule({ ...rule, digits: Number(event.target.value) })}/></label>
      </div>
      <p>Use {'{base}'} e {'{number}'}. Ex.: {'{base}_{number}'} → denia_001.png. A extensão original é preservada.</p>
      <label className="assets-naming-toggle"><input type="checkbox" checked={rule.autoContinue}
        onChange={event => onRule({ ...rule, autoContinue: event.target.checked })}/> Continuar após o maior número existente no destino</label>
      {!rule.autoContinue && <label>Começar em<input type="number" min="0" max="999999999" value={rule.startNumber}
        onChange={event => onRule({ ...rule, startNumber: Number(event.target.value) })}/></label>}
    </>}
    <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
      <summary>Escolher ordem e nomes · {items.length} itens</summary>
      <label>Ordenar arquivos<select value={sort} onChange={event => orderBy(event.target.value)}>
        <option value="selection">Ordem da seleção</option><option value="name">Nome</option>
        <option value="oldest">Mais antigos primeiro</option><option value="newest">Mais recentes primeiro</option>
        <option value="manual">Ordem manual</option></select></label>
      <p>Arraste pela alça ou use as setas. A numeração segue esta ordem; itens ignorados não recebem número.</p>
      <div className="assets-naming-list" role="list" aria-label="Ordem dos arquivos">
        {items.map((item, index) => <div role="listitem" key={item.id} className={'assets-naming-item' + (conflicts.includes(item.id) ? ' conflict' : '')}
          onDragOver={event => { if (dragged) event.preventDefault(); }}
          onDrop={event => { event.preventDefault(); move(items.findIndex(value => value.id === dragged), index); setDragged(''); }}>
          <button type="button" className="title-btn" draggable={!busy} aria-label={`Arrastar ${item.name}`}
            onDragStart={event => { setDragged(item.id); event.dataTransfer.setData('text/plain', item.id); event.dataTransfer.effectAllowed = 'move'; }}
            onDragEnd={() => setDragged('')}><GripVertical size={16}/></button>
          <span className="assets-naming-number">{index + 1}</span>
          {item.isImage ? <img loading="lazy" src={mediaUrl(item, 'thumb')} alt=""/> : <span/>}
          <div className="assets-naming-item-info"><strong title={item.relativePath}>{item.name}</strong>
            <small title={item.relativePath}>{item.relativePath}</small>
            {conflicts.includes(item.id) && <span className="assets-naming-conflict">Nome em conflito na última prévia</span>}
            <select aria-label={`Ação para ${item.name} · ${index + 1}`} value={choices[item.id]?.action || 'default'}
              onChange={event => onChoice(item.id, event.target.value === 'default' ? null : {
                assetId: item.id, action: event.target.value as AssetFileChoice['action'], name: choices[item.id]?.name || item.name })}>
              <option value="default">Usar regra / nome atual</option><option value="rename">Definir nome específico</option><option value="skip">Ignorar este item</option></select>
            {choices[item.id]?.action === 'rename' && <input aria-label={`Novo nome de ${item.name} · ${index + 1}`}
              value={choices[item.id].name} maxLength={240} onChange={event => onChoice(item.id, { ...choices[item.id], name: event.target.value })}/>}
          </div>
          <div className="assets-naming-order-buttons"><button type="button" className="title-btn" disabled={index === 0} aria-label={`Subir ${item.name} · ${index + 1}`} onClick={() => move(index, index - 1)}><ArrowUp size={16}/></button>
            <button type="button" className="title-btn" disabled={index === items.length - 1} aria-label={`Descer ${item.name} · ${index + 1}`} onClick={() => move(index, index + 1)}><ArrowDown size={16}/></button></div>
        </div>)}
      </div>
    </details>
  </fieldset>;
}
