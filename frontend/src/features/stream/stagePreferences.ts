import { constrainRect, type TileRect } from './stageLayout';

export type StageMode = 'grid' | 'free' | 'spotlight';
export interface StagePreferences { version: 1; mode: StageMode; showLocal: boolean; snap: boolean; slots: TileRect[] }
export const STAGE_PREFERENCES_KEY = 'xennex_stream_layout_v1';
export const defaultStagePreferences = (): StagePreferences => ({ version: 1, mode: 'grid', showLocal: true, snap: false, slots: [] });

/** Persist anonymous visual slots, never participant/publication IDs, names or room codes. */
export function parseStagePreferences(raw: string | null): StagePreferences {
  const fallback = defaultStagePreferences();
  if (!raw || raw.length > 12000) return fallback;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object' || !('version' in value) || value.version !== 1) return fallback;
    const data = value as Record<string, unknown>;
    const slots = Array.isArray(data.slots) ? data.slots.slice(0, 32).flatMap(slot => {
      if (!slot || typeof slot !== 'object') return [];
      if (!['x', 'y', 'width', 'height'].every(key => typeof slot[key] === 'number' && Number.isFinite(slot[key]))) return [];
      return [constrainRect({ x: slot.x, y: slot.y, width: slot.width, height: slot.height })];
    }) : [];
    return { version: 1, mode: data.mode === 'free' || data.mode === 'spotlight' ? data.mode : 'grid', showLocal: data.showLocal !== false, snap: data.snap === true, slots };
  } catch { return fallback; }
}
export function readStagePreferences(): StagePreferences {
  try { return parseStagePreferences(localStorage.getItem(STAGE_PREFERENCES_KEY)); }
  catch { return defaultStagePreferences(); }
}
export function writeStagePreferences(preferences: StagePreferences): boolean {
  try {
    const safe = parseStagePreferences(JSON.stringify(preferences));
    localStorage.setItem(STAGE_PREFERENCES_KEY, JSON.stringify(safe)); return true;
  } catch { return false; }
}
