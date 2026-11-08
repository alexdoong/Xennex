import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type KeyboardEvent } from 'react';
import { GripHorizontal, MoveDiagonal2, ScreenShare } from 'lucide-react';
import StreamVideo from './StreamVideo';
import { constrainRect, initialRect, snapTransformRect, transformRect, type TileGesture, type TileRect } from './stageLayout';
import { readStagePreferences, writeStagePreferences, defaultStagePreferences, type StageMode } from './stagePreferences';
import type { VideoReading } from './streamStats';
import type { Quality } from './quality';
import './stream-stage.css';

interface Tile { id: string; stream: MediaStream; name: string; local: boolean; quality?: Quality }
interface Props { tiles: Tile[]; readings: Record<string, VideoReading>; audible: string[]; focus: string; onAudio(id: string): void; onFocus(id: string): void }
const edges: TileGesture[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'sw', 'se'];
export default function StreamStage({ tiles, readings, audible, focus, onAudio, onFocus }: Props) {
  const [saved, setSaved] = useState(readStagePreferences);
  const [mode, setMode] = useState<StageMode>(saved.mode);
  const free = mode === 'free';
  const [showLocal, setShowLocal] = useState(saved.showLocal);
  const [snap, setSnap] = useState(saved.snap);
  const [positions, setPositions] = useState<Record<string, TileRect>>({});
  const [layoutNotice, setLayoutNotice] = useState('');
  const [front, setFront] = useState('');
  const board = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(540);
  useLayoutEffect(() => {
    const element = board.current;
    if (!element) return;
    const update = () => setHeight(Math.max(320, Math.floor(window.innerHeight - element.getBoundingClientRect().top - 24)));
    const observer = new ResizeObserver(update);
    const workspace = element.closest('section');
    observer.observe(workspace || element);
    workspace?.querySelectorAll('.room-toolbar,.room-header,.room-view-tools,.room-notice,.room-layout-help').forEach(target => observer.observe(target));
    window.addEventListener('resize', update); update();
    return () => { observer.disconnect(); window.removeEventListener('resize', update); };
  }, [mode, focus, layoutNotice]);
  const gesture = useRef<{ id: string; pointer: number; x: number; y: number; width: number; height: number; rect: TileRect; mode: TileGesture } | undefined>(undefined);
  const visible = tiles.filter(tile => !tile.local || showLocal);
  const validFocus = visible.some(tile => tile.id === focus) ? focus : mode === 'spotlight' ? visible[0]?.id || '' : '';
  const thumbnails = mode === 'spotlight' && !!validFocus;
  const floating = free && !validFocus;
  const rectFor = (id: string) => constrainRect(positions[id] || saved.slots[Math.max(0, tiles.findIndex(tile => tile.id === id))] ||
    initialRect(Math.max(0, visible.findIndex(tile => tile.id === id)), visible.length, board.current?.clientWidth, height),
    240 / Math.max(240, board.current?.clientWidth || 1200), 160 / Math.max(160, height));
  const tileKey = JSON.stringify(tiles.map(tile => tile.id));
  useEffect(() => {
    const ids: string[] = JSON.parse(tileKey);
    setPositions(current => Object.fromEntries(ids.flatMap(id => current[id] ? [[id, current[id]]] : [])));
  }, [tileKey]);
  const changeMode = (next: StageMode) => { setMode(next); onFocus(''); setLayoutNotice(''); };
  const save = () => {
    const preferences = { version: 1 as const, mode, showLocal, snap, slots: tiles.map(tile => rectFor(tile.id)).slice(0, 32) };
    setSaved(preferences);
    setLayoutNotice(writeStagePreferences(preferences) ? 'Organização salva neste dispositivo, pela ordem das telas.' : 'Não foi possível salvar neste navegador. A organização continua disponível nesta sessão.');
  };
  const reset = () => {
    const preferences = defaultStagePreferences();
    setSaved(preferences); setPositions({}); setMode('grid'); setShowLocal(true); setSnap(false); onFocus('');
    setLayoutNotice(writeStagePreferences(preferences) ? 'Organização padrão restaurada.' : 'Padrão restaurado nesta sessão; o navegador não permitiu salvar.');
  };
  const start = (event: PointerEvent<HTMLButtonElement>, id: string, mode: TileGesture) => {
    if (event.button !== 0 || !board.current) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); setFront(id);
    gesture.current = { id, pointer: event.pointerId, x: event.clientX, y: event.clientY,
      width: board.current.clientWidth, height: board.current.clientHeight, rect: rectFor(id), mode };
  };
  const move = (event: PointerEvent<HTMLButtonElement>) => {
    const drag = gesture.current;
    if (!drag || drag.pointer !== event.pointerId) return;
    const dx = (event.clientX - drag.x) / Math.max(1, drag.width), dy = (event.clientY - drag.y) / Math.max(1, drag.height);
    const rect = (snap ? snapTransformRect : transformRect)(drag.rect, dx, dy, drag.mode, 240 / Math.max(1, drag.width), 160 / Math.max(1, drag.height));
    setPositions(current => ({ ...current, [drag.id]: rect }));
  };
  const key = (event: KeyboardEvent<HTMLButtonElement>, id: string, mode: TileGesture) => {
    const delta = { ArrowLeft: [-.02, 0], ArrowRight: [.02, 0], ArrowUp: [0, -.02], ArrowDown: [0, .02] }[event.key];
    if (!delta) return;
    event.preventDefault(); setFront(id);
    const rect = rectFor(id);
    setPositions(current => ({ ...current, [id]: (snap ? snapTransformRect : transformRect)(rect, delta[0], delta[1], mode,
      240 / Math.max(1, board.current?.clientWidth || 1), 160 / Math.max(1, board.current?.clientHeight || 1)) }));
  };
  const handle = (id: string, mode: TileGesture) => ({
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => start(event, id, mode),
    onPointerMove: move, onPointerUp: () => { gesture.current = undefined; },
    onPointerCancel: () => { gesture.current = undefined; }, onLostPointerCapture: () => { gesture.current = undefined; },
    onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => key(event, id, mode),
  });
  return <div className="room-screen-area">
    <div className="room-view-tools" aria-label="Organização das telas">
      <button aria-pressed={mode === 'grid'} onClick={() => changeMode('grid')}>Grade</button>
      <button aria-pressed={free} onClick={() => changeMode('free')}>Organizar livremente</button>
      <button aria-pressed={mode === 'spotlight'} onClick={() => changeMode('spotlight')}>Foco e miniaturas</button>
      {free && <button aria-pressed={snap} onClick={() => setSnap(value => !value)}>Encaixar na grade</button>}
      {free && <button onClick={() => { setPositions({}); onFocus(''); }}>Reorganizar telas</button>}
      <button aria-pressed={showLocal} onClick={() => setShowLocal(value => !value)}>{showLocal ? 'Ocultar minhas prévias' : 'Mostrar minhas prévias'}</button>
      {validFocus && <button onClick={() => changeMode('grid')}>Voltar a todas as telas</button>}
      <button onClick={save}>Salvar organização</button>
      <button onClick={reset}>Restaurar padrão</button>
    </div>
    {layoutNotice && <small className="room-layout-help" role="status">{layoutNotice}</small>}
    {floating && <small className="room-layout-help">Arraste pelo título, redimensione pelas bordas ou cantos. Duplo clique no vídeo para destacar. As alças também aceitam as setas do teclado.</small>}
    <div ref={board} className={`room-grid ${validFocus && !thumbnails ? 'room-grid-focus' : ''} ${thumbnails ? 'room-spotlight-board' : ''} ${floating ? 'room-free-board' : ''}`}
      style={{ height }}>
      {tiles.map(tile => {
        const hidden = (!showLocal && tile.local) || (!!validFocus && !thumbnails && tile.id !== validFocus);
        const rect = rectFor(tile.id);
        return <div key={tile.id} inert={hidden} aria-hidden={hidden}
          className={hidden ? 'room-background-media' : `room-tile ${floating ? 'room-floating-tile' : ''} ${thumbnails && tile.id === validFocus ? 'room-spotlight-primary' : ''}`}
          style={!hidden && floating ? { left: `${rect.x * 100}%`, top: `${rect.y * 100}%`, width: `${rect.width * 100}%`, height: `${rect.height * 100}%`, zIndex: front === tile.id ? 2 : 1 } : !hidden && thumbnails ? { order: tile.id === validFocus ? -1 : 0 } : undefined}
          onPointerDown={() => setFront(tile.id)}>
          <button className="room-move-handle" hidden={!floating || hidden} aria-label={`Mover ${tile.name}`} {...handle(tile.id, 'move')}><GripHorizontal size={16}/><span>{tile.name}</span></button>
          <StreamVideo {...tile} reading={readings[tile.id]} audible={audible.includes(tile.id)} focused={tile.id === validFocus}
            onAudio={() => onAudio(tile.id)} onFocus={() => onFocus(validFocus === tile.id ? '' : tile.id)}/>
          {edges.map(edge => <button key={edge} className={`room-resize-handle room-resize-${edge}`} hidden={!floating || hidden}
            aria-label={edge === 'se' ? `Redimensionar ${tile.name}` : `Redimensionar borda ${edge}: ${tile.name}`} {...handle(tile.id, edge)}>
            {edge === 'se' && <MoveDiagonal2 size={16}/>}
          </button>)}
        </div>;
      })}
      {!visible.length && <div className="room-empty"><ScreenShare size={40}/><h3>Nenhuma tela visível</h3><p>Escolha uma transmissão na lista de pessoas ou mostre suas prévias.</p><small>O áudio de cada transmissão é ativado por você.</small></div>}
    </div>
  </div>;
}
