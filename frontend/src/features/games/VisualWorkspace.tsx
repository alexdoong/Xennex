import { useEffect, useState } from 'react';
import { LayoutDashboard, Users, Save, Sparkles } from 'lucide-react';
import type { GameVisual, GameCharacter } from './visualTypes';
import { newBoard } from './visualTypes';
import CharacterGallery from './CharacterGallery';
import StrategyPlanner from './StrategyPlanner';
import ImagePicker from './ImagePicker';
import type { GameDefinition } from './definitionTypes';
import SkillOverview from './SkillOverview';

interface Props { definition: GameDefinition; onConfigure: () => void; gameName: string; visual: GameVisual; busy: boolean; error: string; onDirty: (value: boolean) => void; onSave: (visual: GameVisual) => Promise<boolean> }
export default function VisualWorkspace({ definition, onConfigure, gameName, visual, busy, error, onDirty, onSave }: Props) {
  const [draft, setDraft] = useState<GameVisual>(visual);
  const [imageLoading, setImageLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState(false);
  const [view, setView] = useState<'characters' | 'skills' | 'plans'>(definition.hasEntities ? 'characters' : 'skills');
  const [activeBoard, setActiveBoard] = useState('');
  useEffect(() => { onDirty(dirty || editing || imageLoading); }, [dirty, editing, imageLoading, onDirty]);
  useEffect(() => { if (!dirty && !editing && !imageLoading) setDraft(visual); }, [visual, dirty, editing, imageLoading]);
  const change = (value: GameVisual) => { setDraft(value); setDirty(true); };
  const addToPlan = (character: GameCharacter) => {
    const board = draft.boards.find(b => b.id === activeBoard) ?? draft.boards[0] ?? newBoard('Minha composição');
    if (board.cards.length >= 60) { setActiveBoard(board.id); setView('plans'); return; }
    const next = { ...board, cards: [...board.cards, { id: crypto.randomUUID(), characterId: character.id, title: character.name,
      notes: '', color: character.color, x: 40 + board.cards.length % 5 * 225, y: 100 + Math.floor(board.cards.length / 5) % 2 * 250 }] };
    change({ ...draft, boards: draft.boards.some(b => b.id === board.id) ? draft.boards.map(b => b.id === board.id ? next : b) : [...draft.boards, next] });
    setActiveBoard(board.id); setView('plans');
  };
  return <div className="games-visual">
    <div className="games-hero">
      {draft.cover && <img className="games-hero-image" src={draft.cover} alt="" />}
      <div className="games-hero-content"><span className="games-eyebrow"><Sparkles size={14} /> SEU ESPAÇO CRIATIVO</span><h2>{gameName}</h2>
        <p>{definition.hasEntities ? 'Monte suas composições. Conecte ideias. Explore estratégias.' : 'Explore suas habilidades. Planeje treinos. Acompanhe sua evolução.'}</p>
        <div className="games-hero-counts"><span>{definition.category}</span><span>{definition.hasEntities ? draft.characters.length + ' ' + definition.entityLabel.toLocaleLowerCase() : definition.skills.filter(s => !s.archived).length + ' habilidades'}</span><span>{draft.boards.length} planos</span></div>
      </div>
      <div className="games-hero-tools"><ImagePicker label="Escolher capa do jogo" value={draft.cover} cover disabled={busy || editing || imageLoading} onLoading={setImageLoading} onChange={cover => { setDraft(previous => ({ ...previous, cover })); setDirty(true); }} /></div>
    </div>
    <div className="games-visual-toolbar">
      <div className="games-view-tabs" role="group" aria-label="Área visual">
        {definition.hasEntities && <button className={'btn ' + (view === 'characters' ? 'primary' : 'secondary')} disabled={busy || editing || imageLoading} onClick={() => setView('characters')}><Users size={16} />{definition.entityLabel}</button>}
        <button className={'btn ' + (view === 'skills' ? 'primary' : 'secondary')} disabled={busy || editing || imageLoading} onClick={() => setView('skills')}><Users size={16} />Habilidades</button>
        <button className={'btn ' + (view === 'plans' ? 'primary' : 'secondary')} disabled={busy || editing || imageLoading} onClick={() => setView('plans')}><LayoutDashboard size={16} />Planejamento</button>
      </div>
      <div className="games-board-tools"><span className={dirty ? 'games-dirty' : 'games-muted'} role="status">{editing ? 'Finalize o personagem para salvar' : imageLoading ? 'Preparando imagem…' : dirty ? 'Alterações não salvas' : 'Tudo salvo'}</span>
        {dirty && <button className="btn secondary" disabled={busy || editing || imageLoading} onClick={() => { setDraft(visual); setDirty(false); }}>Descartar alterações</button>}
        <button className="btn primary" disabled={!dirty || busy || editing || imageLoading} onClick={async () => { if (await onSave(draft)) setDirty(false); }}><Save size={15} />Salvar espaço visual</button>
      </div>
    </div>
    {error && <p className="games-error" role="alert">{error}</p>}
    {view === 'skills' || (view === 'characters' && !definition.hasEntities) ? <SkillOverview definition={definition} disabled={busy || dirty || editing} onConfigure={onConfigure} /> : view === 'characters' ? <CharacterGallery label={definition.entityLabel} characters={draft.characters} busy={busy || imageLoading} onEditing={setEditing}
      onChange={characters => change({ ...draft, characters, boards: draft.boards.map(b => ({ ...b, cards: b.cards.map(c => characters.some(item => item.id === c.characterId) ? c : { ...c, characterId: '' }) })) })} onPlan={addToPlan} /> :
      <StrategyPlanner entityLabel={definition.entityLabel} hasEntities={definition.hasEntities} boards={draft.boards} characters={draft.characters} active={activeBoard} busy={busy || imageLoading} onActive={setActiveBoard} onChange={boards => change({ ...draft, boards })} />}
  </div>;
}
