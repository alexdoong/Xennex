import { useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import type { AssetFileChoice, AssetItem, AssetNamingRule, AssetRoot } from './types';
import AssetDestinationPicker from './AssetDestinationPicker';
import AssetNamingEditor from './AssetNamingEditor';

type Operation = 'createFolder' | 'rename' | 'copy' | 'move' | 'recycle';
interface PlanItem { assetId: string; sourcePath: string; destinationPath: string; isDirectory: boolean; conflict: boolean; skipped: boolean; note: string }
interface Plan { id: string; type: Operation; items: PlanItem[]; expiresUtc: number; canExecute: boolean; startNumber: number | null }
type Props = { type: Operation; items: AssetItem[]; roots: AssetRoot[]; rootId: string; folder: string; targetRootId?: string; targetFolder?: string;
  onClose: () => void; onStarted: (jobId: string) => void };

const titles: Record<Operation, string> = {
  createFolder: 'Criar pasta', rename: 'Renomear', copy: 'Copiar arquivos', move: 'Mover arquivos', recycle: 'Enviar à Lixeira'
};

export default function AssetFileActions({ type, items, roots, rootId, folder, targetRootId, targetFolder, onClose, onStarted }: Props) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [destinationRootId, setDestinationRootId] = useState(targetRootId || rootId);
  const [destinationFolder, setDestinationFolder] = useState(targetFolder ?? folder);
  const [newName, setNewName] = useState(type === 'rename' ? items[0]?.name || '' : '');
  const [ordered, setOrdered] = useState(items);
  const [namingEnabled, setNamingEnabled] = useState(type === 'rename' && items.length > 1 && items.every(item => !item.isDirectory));
  const [naming, setNaming] = useState<AssetNamingRule>({ baseName: 'arte', pattern: '{base}{number}', scope: 'all', autoContinue: true, startNumber: 1, digits: 1 });
  const [choices, setChoices] = useState<Record<string, AssetFileChoice>>({});
  const [conflictPolicy, setConflictPolicy] = useState('ask');
  const [plan, setPlan] = useState<Plan | null>(null);
  const [dirty, setDirty] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const conflicts = useMemo(() => plan?.items.filter(item => item.conflict).map(item => item.assetId) || [], [plan]);
  const namingOperation = type === 'rename' || type === 'copy' || type === 'move';
  const invalidate = () => { setDirty(true); setError(''); };
  const preview = async () => {
    if (!api || busy) return;
    setBusy(true); setError(''); setPlan(null);
    try {
      const request = { type, assetIds: ordered.map(item => item.id), destinationRootId, destinationFolder, newName,
        conflictPolicy, naming: namingEnabled ? naming : null, choices: Object.values(choices) };
      const result = JSON.parse(await api.PlanAssetFileOperation(JSON.stringify(request))) as Plan;
      if (typeof result.canExecute !== 'boolean') throw new Error('Atualize o executável do Xennex para usar decisões de nomes em lote.');
      setPlan(result); setDirty(false);
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };
  const execute = async () => {
    if (!api || !plan || busy || dirty || !plan.canExecute) return;
    setBusy(true); setError('');
    try { onStarted(await api.ExecuteAssetFileOperation(plan.id)); onClose(); }
    catch (reason) { setError(String(reason)); setPlan(null); }
    finally { setBusy(false); }
  };
  return <div className="assets-operation-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={'assets-operation' + (namingOperation ? ' assets-file-operation' : '')} role="dialog" aria-modal="true" aria-label={titles[type]}>
      <header><h2>{titles[type]}</h2><button className="title-btn" onClick={onClose} aria-label="Fechar"><X size={19}/></button></header>
      <p>{type === 'recycle' ? 'Os arquivos selecionados serão enviados à Lixeira do Windows.' :
        type === 'copy' ? 'A cópia cria novos arquivos; seus originais continuam no lugar.' :
        type === 'move' ? 'O destino será verificado antes de retirar a origem.' :
        'Confira o nome e o destino antes de continuar.'}</p>
      {(type === 'createFolder' || type === 'rename' && items.length === 1 && !namingEnabled) && <label>Nome<input autoFocus disabled={busy} value={newName} maxLength={240} onChange={event => { setNewName(event.target.value); invalidate(); }}/></label>}
      {(type === 'createFolder' || type === 'copy' || type === 'move') && <>
        <AssetDestinationPicker roots={roots} rootId={destinationRootId} folder={destinationFolder}
          onChange={(id, path) => { if (busy) return; setDestinationRootId(id); setDestinationFolder(path); invalidate(); }}/>
      </>}
      {namingOperation && <>
        <label>Se o nome estiver ocupado<select disabled={busy} value={conflictPolicy} onChange={event => { setConflictPolicy(event.target.value); invalidate(); }}>
          <option value="ask">Escolher por arquivo na prévia</option><option value="rename">Renomear automaticamente os conflitos</option>
          <option value="skip">Ignorar os arquivos em conflito</option></select></label>
        <AssetNamingEditor items={ordered} enabled={namingEnabled} rule={naming} choices={choices} conflicts={conflicts} busy={busy}
          onEnabled={value => { setNamingEnabled(value); invalidate(); }} onRule={value => { setNaming(value); invalidate(); }}
          onOrder={value => { setOrdered(value); invalidate(); }} onChoice={(id, value) => { setChoices(old => {
            const next = { ...old }; if (value) next[id] = value; else delete next[id]; return next;
          }); invalidate(); }}/>
      </>}
      {error && <p role="alert" className="assets-alert">{error}</p>}
      <button className="btn primary" disabled={busy || ((type === 'createFolder' || type === 'rename' && items.length === 1 && !namingEnabled && !choices[items[0].id]) && !newName.trim())} onClick={() => void preview()}>{busy ? 'Verificando…' : plan && dirty ? 'Atualizar prévia' : 'Ver prévia'}</button>
      {plan && <>
        <p><strong>{plan.items.filter(item => !item.skipped).length} item(ns) ativos</strong> · {plan.items.filter(item => item.skipped).length} ignorados · prévia válida por cinco minutos</p>
        {plan.startNumber != null && <p>Numeração calculada começa em <strong>{plan.startNumber}</strong>.</p>}
        {dirty && <p role="status">As opções mudaram. Atualize a prévia antes de confirmar.</p>}
        {!dirty && conflicts.length > 0 && <p role="alert">{conflicts.length} conflito(s). Em “Escolher ordem e nomes”, defina um nome específico ou ignore esses itens; depois atualize a prévia.</p>}
        {!dirty && !plan.canExecute && !conflicts.length && <p role="status">Nenhum item precisa ser alterado com estas opções.</p>}
        <div className="assets-operation-list">{plan.items.map((item, index) => <div key={index} className={item.conflict ? 'conflict' : item.skipped ? 'skipped' : ''}>
          {item.sourcePath && <small>Origem: {item.sourcePath}</small>}
          <strong>{item.skipped ? 'Ignorado: ' + item.destinationPath : type === 'recycle' ? 'Destino: Lixeira do Windows' : 'Destino: ' + item.destinationPath}</strong>
          {item.note && <small>{item.note}</small>}
        </div>)}</div>
        <div className="assets-operation-buttons"><button className="btn secondary" onClick={() => setPlan(null)}>Alterar</button><button className="btn primary" disabled={busy || dirty || !plan.canExecute} onClick={() => void execute()}>{busy ? 'Iniciando…' : 'Confirmar ' + titles[type].toLowerCase()}</button></div>
      </>}
    </section>
  </div>;
}
