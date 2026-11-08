import { useEffect, useRef, useState } from 'react';
import type { GameCharacter, StrategyBoard, StrategyCard } from './visualTypes';

interface Props { board: StrategyBoard; characters: GameCharacter[]; selected: string; busy: boolean; onSelect: (id: string) => void; onChange: (board: StrategyBoard) => void }
const clamp = (value: number, max: number) => Math.min(max, Math.max(0, Math.round(value)));
export default function StrategyCanvas({ board, characters, selected, busy, onSelect, onChange }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState(1200);
  const [zoom, setZoom] = useState<number | null>(null);
  const scale = zoom ?? Math.min(1, Math.max(.25, available / 1200));
  const drag = useRef<{ id: string; pointer: number; x: number; y: number; left: number; top: number; scale: number } | null>(null);
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    const observer = new ResizeObserver(() => { if (node.clientWidth) setAvailable(node.clientWidth - 2); });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const move = (card: StrategyCard, x: number, y: number) => {
    onChange({ ...board, cards: board.cards.map(c => c.id === card.id ? { ...c, x: clamp(x, 1000), y: clamp(y, 550) } : c) });
  };
  return <div className="games-canvas-frame" ref={container}>
    <div className="games-canvas-controls"><span>QUADRO LIVRE</span><div>
      <button type="button" className="btn secondary" aria-label="Diminuir zoom" onClick={() => setZoom(Math.max(.25, scale - .1))}>−</button>
      <span aria-label="Zoom do quadro">{Math.round(scale * 100)}%</span>
      <button type="button" className="btn secondary" aria-label="Aumentar zoom" onClick={() => setZoom(Math.min(1.5, scale + .1))}>+</button>
      <button type="button" className="btn secondary" onClick={() => setZoom(null)}>Ajustar quadro</button>
    </div></div>
    <div className="games-board-scroll" aria-label="Área do planejamento">
    <div style={{ width: 1200 * scale, height: 760 * scale }}>
    <div className="games-board-canvas" style={{ transform: 'scale(' + scale + ')', transformOrigin: 'top left' }}>
      <div className="games-board-watermark">PLANEJAMENTO LIVRE <span>Arraste os cartões · Use as setas do teclado para ajustes</span></div>
      <svg className="games-board-links" viewBox="0 0 1200 760" aria-label="Conexões entre cartões">
        <defs><marker id="games-strategy-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#c4b5fd" /></marker></defs>
        {board.links.map(link => {
          const a = board.cards.find(c => c.id === link.from), b = board.cards.find(c => c.id === link.to);
          if (!a || !b) return null;
          const right = b.x >= a.x, x1 = a.x + (right ? 200 : 0), x2 = b.x + (right ? 0 : 200);
          const bend = Math.max(50, Math.abs(x2 - x1) / 2) * (right ? 1 : -1);
          return <path key={link.from + link.to} d={'M' + x1 + ',' + (a.y + 105) + ' C' + (x1 + bend) + ',' + (a.y + 105) + ' ' + (x2 - bend) + ',' + (b.y + 105) + ' ' + x2 + ',' + (b.y + 105)} fill="none" stroke="#c4b5fd" strokeWidth="2" markerEnd="url(#games-strategy-arrow)"><title>{a.title + ' → ' + b.title}</title></path>;
        })}
      </svg>
      {board.cards.map(card => {
        const character = characters.find(c => c.id === card.characterId);
        return <button type="button" key={card.id} data-card-id={card.id} aria-label={'Cartão ' + card.title} aria-pressed={selected === card.id}
          className={'games-board-card ' + (selected === card.id ? 'is-selected' : '')}
          style={{ left: card.x, top: card.y, borderColor: card.color, backgroundColor: card.color + '18' }} disabled={busy}
          onClick={() => onSelect(card.id)}
          onPointerDown={event => {
            if (event.button !== 0 || busy) return;
            onSelect(card.id); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId);
            drag.current = { id: card.id, pointer: event.pointerId, x: event.clientX, y: event.clientY, left: card.x, top: card.y, scale };
          }}
          onPointerMove={event => {
            const start = drag.current;
            if (!start || start.id !== card.id || start.pointer !== event.pointerId || busy) return;
            move(card, start.left + (event.clientX - start.x) / start.scale, start.top + (event.clientY - start.y) / start.scale);
          }}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
          onLostPointerCapture={() => { drag.current = null; }}
          onKeyDown={event => {
            const step = event.shiftKey ? 40 : 10;
            if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
            event.preventDefault();
            move(card, card.x + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0),
              card.y + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0));
          }}>
          {character?.image ? <img src={character.image} alt="" draggable={false} style={{ objectPosition: 'center ' + character.focus + '%' }} /> : <span className="games-card-symbol" style={{ color: card.color }}>{character ? character.name.slice(0, 2).toUpperCase() : '✦'}</span>}
          <span className="games-board-card-copy"><small>{character?.role || (character ? 'Personagem' : 'Anotação')}</small><strong>{card.title}</strong><span>{card.notes || character?.notes || 'Selecione para adicionar detalhes'}</span></span>
        </button>;
      })}
      {!board.cards.length && <div className="games-board-empty"><h3>Comece a desenhar sua estratégia</h3><p>Adicione personagens e anotações. Posicione, conecte e explore possibilidades.</p></div>}
    </div></div></div>
  </div>;
}
