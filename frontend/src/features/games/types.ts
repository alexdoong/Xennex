import type { GameVisual } from './visualTypes';
import { emptyVisual } from './visualTypes';
import type { GameDefinition, SessionContext, SessionEvent } from './definitionTypes';
import { definitionFor } from './definitionTypes';
export interface GameMetric { definitionId?: string; name: string; value: number; unit: string }
export interface GameSession {
  id: string; title: string; occurredAt: string; createdAt: string; updatedAt: string;
  patch: string; context: string; notes: string; source: 'manual'; metrics: GameMetric[];
  contextValues?: SessionContext[]; events?: SessionEvent[];
}
export interface GameDocument {
  schemaVersion: 1 | 2 | 3; definition?: GameDefinition; visual?: GameVisual; id: string; name: string; revision: number; sessions: GameSession[];
}
export interface GameLibrary { games: GameDocument[]; warnings: string[] }
export const metricKey = (metric: GameMetric) =>
  JSON.stringify([metric.definitionId || metric.name.trim().toLocaleLowerCase('pt-BR'), metric.unit.trim().toLocaleLowerCase('pt-BR')]);
export const displayDate = (date: string) => new Date(date).toLocaleString('pt-BR');
export const localDate = (date: string) => {
  const value = new Date(date);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export const normalizeGame = (game: GameDocument): GameDocument => ({ ...game, schemaVersion: 3, visual: game.visual ?? emptyVisual(), definition: game.definition ?? definitionFor('Personalizado') });
