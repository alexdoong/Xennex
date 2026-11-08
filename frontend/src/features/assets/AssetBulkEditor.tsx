import { useState } from 'react';
import { X } from 'lucide-react';
import type { AssetCollection, AssetItem } from './types';

export type AssetBulkChanges = {
  favorite: boolean | null;
  addTag: string | null;
  removeTag: string | null;
  collectionId: string | null;
  collectionPresent: boolean | null;
};

type Props = {
  items: AssetItem[];
  collections: AssetCollection[];
  busy: boolean;
  onClose: () => void;
  onApply: (changes: AssetBulkChanges) => void;
};

export default function AssetBulkEditor({ items, collections, busy, onClose, onApply }: Props) {
  const [favorite, setFavorite] = useState<'keep' | 'yes' | 'no'>('keep');
  const [addTag, setAddTag] = useState('');
  const [removeTag, setRemoveTag] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [collectionAction, setCollectionAction] = useState<'add' | 'remove'>('add');
  const changed = favorite !== 'keep' || !!addTag.trim() || !!removeTag.trim() || !!collectionId;
  return <div className="assets-operation-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="assets-operation assets-bulk-editor" role="dialog" aria-modal="true" aria-label="Editar seleção">
      <header><h2>Editar {items.length} itens</h2><button className="title-btn" onClick={onClose} aria-label="Fechar edição em lote"><X size={18}/></button></header>
      <p>As mudanças abaixo serão aplicadas a todos os itens selecionados. Os arquivos originais não serão alterados.</p>
      <div className="assets-bulk-preview">{items.slice(0, 8).map(item => <span key={item.id} title={item.relativePath}>{item.name}</span>)}
        {items.length > 8 && <span>+ {items.length - 8} outros</span>}</div>
      <div className="assets-bulk-field"><label htmlFor="assets-bulk-favorite">Favoritos</label><select id="assets-bulk-favorite" value={favorite} onChange={event => setFavorite(event.target.value as 'keep' | 'yes' | 'no')}>
        <option value="keep">Não alterar</option><option value="yes">Marcar como favorito</option><option value="no">Remover dos favoritos</option>
      </select></div>
      <div className="assets-bulk-tags"><label>Adicionar tag <input value={addTag} maxLength={80} onChange={event => setAddTag(event.target.value)} placeholder="Tag para todos"/></label>
        <label>Remover tag <input value={removeTag} maxLength={80} onChange={event => setRemoveTag(event.target.value)} placeholder="Opcional"/></label></div>
      <div className="assets-bulk-collection"><div className="assets-bulk-field"><label htmlFor="assets-bulk-collection">Coleção</label><select id="assets-bulk-collection" value={collectionId} onChange={event => setCollectionId(event.target.value)}>
        <option value="">Não alterar coleção</option>{collections.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}
      </select></div><div className="assets-bulk-field"><label htmlFor="assets-bulk-action">Ação</label><select id="assets-bulk-action" value={collectionAction} onChange={event => setCollectionAction(event.target.value as 'add' | 'remove')} disabled={!collectionId}>
        <option value="add">Adicionar à coleção</option><option value="remove">Remover da coleção</option>
      </select></div></div>
      {!collections.length && <small>Crie uma coleção na barra lateral para adicioná-la aqui.</small>}
      <div className="assets-operation-buttons"><button className="btn secondary" onClick={onClose}>Cancelar</button>
        <button className="btn primary" disabled={!changed || busy} onClick={() => onApply({
          favorite: favorite === 'keep' ? null : favorite === 'yes', addTag: addTag.trim() || null,
          removeTag: removeTag.trim() || null, collectionId: collectionId || null,
          collectionPresent: collectionId ? collectionAction === 'add' : null
        })}>Aplicar a {items.length} itens</button></div>
    </section>
  </div>;
}
