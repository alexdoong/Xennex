export interface GameCharacter { id: string; name: string; role: string; notes: string; image: string; focus: number; color: string }
export interface StrategyCard { id: string; characterId: string; title: string; notes: string; color: string; x: number; y: number }
export interface StrategyLink { from: string; to: string }
export interface StrategyBoard { id: string; name: string; goal: string; cards: StrategyCard[]; links: StrategyLink[] }
export interface GameVisual { cover: string; characters: GameCharacter[]; boards: StrategyBoard[] }
export const emptyVisual = (): GameVisual => ({ cover: '', characters: [], boards: [] });
export const colors = ['#a78bfa', '#60a5fa', '#34d399', '#fbbf24', '#fb7185', '#f0abfc'];
export const newBoard = (name = 'Novo planejamento'): StrategyBoard =>
  ({ id: crypto.randomUUID(), name, goal: '', cards: [], links: [] });
