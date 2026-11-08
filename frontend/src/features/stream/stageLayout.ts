export interface TileRect { x: number; y: number; width: number; height: number }
export type TileGesture = 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
/** Coordinates are fractions of the board, so a window resize preserves the arrangement. */
export function constrainRect(rect: TileRect, minWidth = .2, minHeight = .15): TileRect {
  const width = clamp(rect.width, Math.min(1, minWidth), 1), height = clamp(rect.height, Math.min(1, minHeight), 1);
  return { width, height, x: clamp(rect.x, 0, 1 - width), y: clamp(rect.y, 0, 1 - height) };
}
export function initialRect(index: number, count: number, boardWidth = 0, boardHeight = 0): TileRect {
  const columns = count <= 1 || (boardWidth > 0 && boardWidth < 600) ? 1 : 2, rows = Math.max(1, Math.ceil(count / columns));
  const height = boardWidth > 0 && boardHeight > 0 ? Math.min(1 / rows, (boardWidth / columns * 9 / 16 + 34) / boardHeight) : 1 / rows;
  return { x: index % columns / columns, y: Math.floor(index / columns) / rows,
    width: 1 / columns, height };
}

export function snapTransformRect(rect: TileRect, dx: number, dy: number, mode: TileGesture, minWidth: number, minHeight: number): TileRect {
  const snap = (value: number) => Math.round(value * 40) / 40;
  const horizontal = mode === 'move' || mode.includes('w') ? rect.x : rect.x + rect.width;
  const vertical = mode === 'move' || mode.includes('n') ? rect.y : rect.y + rect.height;
  return transformRect(rect, snap(horizontal + dx) - horizontal, snap(vertical + dy) - vertical, mode, minWidth, minHeight);
}

/** Resizing keeps the opposite edge anchored, including at board/minimum bounds. */
export function transformRect(rect: TileRect, dx: number, dy: number, mode: TileGesture, minWidth: number, minHeight: number): TileRect {
  const start = constrainRect(rect, minWidth, minHeight);
  if (mode === 'move') return constrainRect({ ...start, x: start.x + dx, y: start.y + dy }, minWidth, minHeight);
  let left = start.x, top = start.y, right = left + start.width, bottom = top + start.height;
  const width = Math.min(1, minWidth), height = Math.min(1, minHeight);
  if (mode.includes('w')) left = clamp(left + dx, 0, right - width);
  if (mode.includes('e')) right = clamp(right + dx, left + width, 1);
  if (mode.includes('n')) top = clamp(top + dy, 0, bottom - height);
  if (mode.includes('s')) bottom = clamp(bottom + dy, top + height, 1);
  return { x: left, y: top, width: right - left, height: bottom - top };
}
