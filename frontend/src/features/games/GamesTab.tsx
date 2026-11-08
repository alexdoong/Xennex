import { useRef, useState } from 'react';
import { useGamesContext } from './GamesContext';
import type { GameDocument, GameSession } from './types';
import SessionEditor from './SessionEditor';
import GameHistory from './GameHistory';
import VisualWorkspace from './VisualWorkspace';
import { emptyVisual } from './visualTypes';
import { definitionFor, gameTypes } from './definitionTypes';
import DefinitionEditor from './DefinitionEditor';

export default function GamesTab() {
  const { games, warnings, busy, error, setError, refresh, save } = useGamesContext();
  const [selected, setSelected] = useState('');
  const [view, setView] = useState<'visual' | 'history' | 'definition'>('visual');
  const [visualDirty, setVisualDirty] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState<string>('Personalizado');
  const [definitionDirty, setDefinitionDirty] = useState(false);
  const [editor, setEditor] = useState<GameSession | 'new' | null>(null);
  const [importing, setImporting] = useState<GameDocument | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const game = games.find(g => g.id === selected) ?? games[0];
  const create = async (event: React.SubmitEvent) => {
    event.preventDefault();
    const result = await save({ schemaVersion: 3, definition: definitionFor(category), visual: emptyVisual(), id: crypto.randomUUID(), name: name.trim(), revision: 0, sessions: [] });
    if (result) { setSelected(result.id); setName(''); setEditor(null); setView('definition'); }
  };
  const exportGame = () => {
    if (!game) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(game, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url; link.download = 'xennex-game-' + game.id + '.json';
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const loadImport = async (file?: File) => {
    if (!file) return;
    setError(''); setImporting(null);
    try {
      if (file.size > 32_000_000) throw Error('O arquivo deve ter até 32 MB.');
      const data = JSON.parse(await file.text()) as GameDocument;
      if (![1, 2, 3].includes(data?.schemaVersion) || typeof data.name !== 'string' || !Array.isArray(data.sessions))
        throw Error('Selecione uma exportação de jogo Xennex, versão 1, 2 ou 3.');
      setImporting(data);
    } catch (e) { setError(String(e)); }
  };
  return <div className="tab-content games-tab">
    <section className="glass-panel">
      <div className="games-toolbar"><div><span className="games-eyebrow">BIBLIOTECA PESSOAL</span><h2>Jogos</h2></div>
        <button className="btn secondary" disabled={busy || !!editor || visualDirty || definitionDirty} onClick={() => void refresh()}>Recarregar</button></div>
      <p className="games-muted">Um espaço para seus personagens, estratégias e experiências.</p>
      <form className="games-add" onSubmit={create}><label>Adicionar jogo<input required maxLength={100} value={name} disabled={busy || !!editor || visualDirty || definitionDirty} onChange={e => setName(e.target.value)} placeholder="Wuthering Waves, LoL, osu!…" /></label>
        <label>Modelo inicial<select aria-label="Modelo inicial" value={category} disabled={busy || !!editor || visualDirty || definitionDirty} onChange={e => setCategory(e.target.value)}>{gameTypes.map(type => <option key={type}>{type}</option>)}</select></label>
        <button className="btn primary" disabled={busy || !!editor || visualDirty || definitionDirty || !name.trim()}>Adicionar jogo</button></form>
      <div className="games-library" aria-label="Biblioteca de jogos">{games.map(item => <button key={item.id} className={'btn ' + (item.id === game?.id ? 'primary' : 'secondary')}
        disabled={busy || !!editor || visualDirty || definitionDirty} aria-pressed={item.id === game?.id} onClick={() => { setSelected(item.id); setEditor(null); }}>{item.name} <small>{item.sessions.length}</small></button>)}</div>
      {!games.length && !busy && <p>Adicione seu primeiro jogo ou importe uma exportação existente.</p>}
      <div className="games-toolbar">
        <button className="btn secondary" disabled={busy || !!editor || visualDirty || definitionDirty} onClick={() => fileInput.current?.click()}>Importar jogo</button>
        {game && <button className="btn secondary" disabled={busy || visualDirty || definitionDirty} onClick={exportGame}>Exportar jogo</button>}
      </div>
      <input ref={fileInput} type="file" accept=".json,application/json" hidden onChange={e => { void loadImport(e.target.files?.[0]); e.target.value = ''; }} />
      {importing && <div className="games-import">
        <h3>Importar “{importing.name}”?</h3><p>{importing.sessions.length} registros. Será criada uma cópia independente; seus jogos atuais serão preservados.</p>
        <div className="games-toolbar"><button className="btn primary" disabled={busy || !!editor || visualDirty || definitionDirty} onClick={async () => {
          const result = await save(importing, true);
          if (result) { setSelected(result.id); setImporting(null); setEditor(null); }
        }}>Importar como cópia</button><button className="btn secondary" disabled={busy} onClick={() => setImporting(null)}>Cancelar importação</button></div>
      </div>}
      {busy && <p role="status">Processando…</p>}
      {error && <p role="alert" className="games-error">{error}</p>}
      {warnings.map(warning => <p role="alert" key={warning}>{warning}</p>)}
    </section>
    {game && <>
      <div className="games-view-tabs" role="group" aria-label="Espaço do jogo"><button className={'btn ' + (view === 'definition' ? 'primary' : 'secondary')} disabled={busy || !!editor || visualDirty || definitionDirty} onClick={() => setView('definition')}>Definir jogo</button><button className={'btn ' + (view === 'visual' ? 'primary' : 'secondary')} disabled={busy || !!editor || visualDirty || definitionDirty} onClick={() => setView('visual')}>Espaço visual</button><button className={'btn ' + (view === 'history' ? 'primary' : 'secondary')} disabled={busy || !!editor || visualDirty || definitionDirty} onClick={() => setView('history')}>Histórico e métricas</button></div>
      {view === 'definition' && <DefinitionEditor key={game.id} definition={game.definition!} busy={busy} error={error} onDirty={setDefinitionDirty} onSave={async definition => !!(await save({ ...game, definition }))} />}
      {view === 'visual' && <VisualWorkspace definition={game.definition!} onConfigure={() => setView('definition')} key={game.id} gameName={game.name} visual={game.visual ?? emptyVisual()} busy={busy} error={error} onDirty={setVisualDirty} onSave={async visual => !!(await save({ ...game, visual }))} />}
      {view === 'history' && <>
      <div className="games-toolbar"><h2>{game.name}</h2><button className="btn primary" disabled={busy || !!editor || visualDirty || definitionDirty} onClick={() => setEditor('new')}>Novo registro</button></div>
      {editor && <SessionEditor key={editor === 'new' ? 'new' : editor.id} session={editor === 'new' ? undefined : editor} definition={game.definition!} busy={busy}
        onCancel={() => setEditor(null)} onSave={async session => {
          const result = await save({ ...game, sessions: [...game.sessions.filter(s => s.id !== session.id), session] });
          if (result) setEditor(null);
        }} />}
      <GameHistory key={game.id} sessions={game.sessions} busy={busy || !!editor || visualDirty || definitionDirty} onEdit={session => setEditor(session)} /></>}
    </>}
    <p className="games-muted">Personagens, quadros e registros ficam salvos localmente. Imagens acompanham a exportação. Builds especializadas, calculadoras e sincronização de fontes serão adicionadas nas próximas etapas.</p>
  </div>;
}
