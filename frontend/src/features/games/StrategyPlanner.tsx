import { useState } from 'react';
import { Plus, Copy, StickyNote, Link2 } from 'lucide-react';
import type { GameCharacter, StrategyBoard, StrategyCard } from './visualTypes';
import { colors, newBoard } from './visualTypes';
import StrategyCanvas from './StrategyCanvas';

interface Props { entityLabel: string; hasEntities: boolean; boards: StrategyBoard[]; characters: GameCharacter[]; active: string; busy: boolean; onActive: (id: string) => void; onChange: (boards: StrategyBoard[]) => void }
export default function StrategyPlanner({ entityLabel, hasEntities, boards, characters, active, busy, onActive, onChange }: Props) {
  const [selected, setSelected] = useState('');
  const [characterId, setCharacterId] = useState('');
  const [target, setTarget] = useState('');
  const board = boards.find(b => b.id === active) ?? boards[0];
  const card = board?.cards.find(c => c.id === selected);
  const update = (next: StrategyBoard) => onChange(boards.map(b => b.id === next.id ? next : b));
  const add = (character?: GameCharacter) => {
    if (!board || board.cards.length >= 60) return;
    const next: StrategyCard = { id: crypto.randomUUID(), characterId: character?.id ?? '', title: character?.name ?? 'Nova anotação',
      notes: '', color: character?.color ?? colors[3], x: 40 + board.cards.length % 5 * 225, y: 100 + Math.floor(board.cards.length / 5) % 2 * 250 };
    update({ ...board, cards: [...board.cards, next] }); setSelected(next.id);
  };
  const selectedCharacter = characters.find(c => c.id === characterId) ?? characters[0];
  return <section className="games-planner">
    <div className="games-toolbar"><div><span className="games-eyebrow">EXPLORE POSSIBILIDADES</span><h3>Quadros de estratégia</h3></div>
      <button className="btn secondary" disabled={busy || boards.length >= 24} onClick={() => {
        const next = newBoard('Plano ' + (boards.length + 1)); onChange([...boards, next]); onActive(next.id); setSelected('');
      }}><Plus size={16} />Novo plano</button></div>
    {!!boards.length && <div className="games-plan-tabs" aria-label="Planos">{boards.map(b => <button key={b.id} className={'btn ' + (board?.id === b.id ? 'primary' : 'secondary')} aria-pressed={board?.id === b.id} disabled={busy} onClick={() => { onActive(b.id); setSelected(''); }}>{b.name || 'Plano sem nome'} <small>{b.cards.length}</small></button>)}</div>}
    {!board ? <div className="games-visual-empty"><StickyNote size={36} /><h3>Do personagem à estratégia</h3><p>Crie planos para composições, sequência de habilidades, decisões ou experimentos. Cada plano é um quadro independente.</p></div> : <>
      <div className="games-plan-meta">
        <label>Nome do plano<input value={board.name} maxLength={100} disabled={busy} onChange={e => update({ ...board, name: e.target.value })} /></label>
        <label>Objetivo do plano<input value={board.goal} maxLength={2000} disabled={busy} placeholder="O que você quer testar com esta composição?" onChange={e => update({ ...board, goal: e.target.value })} /></label>
        <button className="btn secondary" disabled={busy || boards.length >= 24} onClick={() => {
          const ids = new Map(board.cards.map(c => [c.id, crypto.randomUUID()]));
          const copy = { ...board, id: crypto.randomUUID(), name: board.name.slice(0, 90) + ' (cópia)',
            cards: board.cards.map(c => ({ ...c, id: ids.get(c.id)! })), links: board.links.map(l => ({ from: ids.get(l.from)!, to: ids.get(l.to)! })) };
          onChange([...boards, copy]); onActive(copy.id); setSelected('');
        }}><Copy size={15} />Duplicar plano</button>
      </div>
      <div className="games-board-tools">
        {hasEntities && <><label>{entityLabel === 'Personagens' ? 'Personagem para o quadro' : 'Peça para o quadro'}<select value={selectedCharacter?.id ?? ''} disabled={busy || !characters.length} onChange={e => setCharacterId(e.target.value)}>
          {!characters.length && <option value="">Crie personagens na galeria</option>}
          {characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <button className="btn secondary" disabled={busy || !selectedCharacter || board.cards.length >= 60} onClick={() => add(selectedCharacter)}><Plus size={15} />Adicionar ao quadro</button></>}
        <button className="btn secondary" disabled={busy || board.cards.length >= 60} onClick={() => add()}><StickyNote size={15} />Adicionar anotação</button>
        <span className="games-muted">{board.cards.length}/60 cartões</span>
      </div>
      <div className="games-planning-surface"><StrategyCanvas board={board} characters={characters} selected={selected} busy={busy} onSelect={setSelected} onChange={update} />
      {card ? <fieldset className="games-card-inspector" disabled={busy}>
        <div className="games-toolbar"><h4>Editar cartão selecionado</h4><button className="btn secondary" onClick={() => {
          update({ ...board, cards: board.cards.filter(c => c.id !== card.id), links: board.links.filter(l => l.from !== card.id && l.to !== card.id) }); setSelected('');
        }}>Remover cartão</button></div>
        <div className="games-fields">
          <label>Título do cartão<input maxLength={100} value={card.title} onChange={e => update({ ...board, cards: board.cards.map(c => c.id === card.id ? { ...c, title: e.target.value } : c) })} /></label>
          <label>Cor do cartão<select value={card.color} onChange={e => update({ ...board, cards: board.cards.map(c => c.id === card.id ? { ...c, color: e.target.value } : c) })}>{colors.map((color, i) => <option key={color} value={color}>{['Lilás', 'Azul', 'Verde', 'Amarelo', 'Rosa', 'Orquídea'][i]}</option>)}</select></label>
        </div>
        <label htmlFor="games-card-notes">Instruções / hipótese</label><textarea id="games-card-notes" rows={3} maxLength={2000} value={card.notes} onChange={e => update({ ...board, cards: board.cards.map(c => c.id === card.id ? { ...c, notes: e.target.value } : c) })} placeholder="Habilidade, prioridade, condição ou alternativa…" />
        <div className="games-board-tools"><label>Conectar com<select value={board.cards.some(c => c.id === target && c.id !== card.id) ? target : ''} onChange={e => setTarget(e.target.value)}><option value="">Escolha outro cartão</option>{board.cards.filter(c => c.id !== card.id).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select></label>
          <button className="btn secondary" disabled={!target || target === card.id || !board.cards.some(c => c.id === target) || board.links.length >= 120 || board.links.some(l => l.from === card.id && l.to === target)}
            onClick={() => update({ ...board, links: [...board.links, { from: card.id, to: target }] })}><Link2 size={15} />Criar conexão</button></div>
        <div className="games-link-list">{board.links.filter(l => l.from === card.id || l.to === card.id).map(link => <div key={link.from + link.to}><span>{board.cards.find(c => c.id === link.from)?.title} → {board.cards.find(c => c.id === link.to)?.title}</span><button className="btn secondary" onClick={() => update({ ...board, links: board.links.filter(l => l !== link) })}>Remover conexão</button></div>)}</div>
      </fieldset> : <aside className="games-card-inspector games-inspector-empty"><Link2 size={24} /><h4>Selecione um cartão</h4><p>Edite instruções, escolha uma cor e conecte os próximos passos.</p></aside>}
      </div>
      <button className="btn secondary" disabled={busy} onClick={() => { onChange(boards.filter(b => b.id !== board.id)); onActive(''); setSelected(''); }}>Remover plano</button>
      <p className="games-muted">Quadro de planejamento manual. As conexões representam suas ideias e não executam comandos ou cálculos do jogo.</p>
    </>}
  </section>;
}
