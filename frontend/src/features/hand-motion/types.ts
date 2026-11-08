export type GestureSource = 'pinch' | 'point' | 'open_palm' | 'swipe_left' | 'swipe_right' | 'swipe_up' | 'swipe_down' | 'pose' | 'motion';
export type ActionType = 'none' | 'shortcut' | 'pointer' | 'drag_window' | 'drag_mouse' | 'scroll' | 'click' | 'right_click' | 'double_click';
export interface GestureBinding {
  id: string; name: string; source: GestureSource; enabled: boolean;
  holdMs: number; cooldownMs: number; threshold: number;
  action: { type: ActionType; value: string };
  samples: { frames: number[][][]; duration: number; hand?: string; legacy?: boolean }[];
}
export interface GestureProfile {
  version: 1; migrationNotice?: string; hand: 'Any' | 'Left' | 'Right'; preview: boolean; smoothing: number;
  swipeThreshold: number; dragTarget: 'titlebar' | 'foreground'; gestures: GestureBinding[];
}
export interface GestureStatus {
  running: boolean; armed: boolean; message: string; recording?: boolean;
  stage?: string; remaining?: number; points?: number[][]; hand?: string;
  metrics?: { fps: number; inferenceMs: number; frameAgeMs: number; recognitionMs?: number };
  match?: string; executed?: boolean; revision: number;
}
export const sources: Record<GestureSource, string> = {
  pinch: 'Pinch (polegar + indicador)', point: 'Indicador estendido', open_palm: 'Palma aberta',
  swipe_left: 'Swipe à esquerda', swipe_right: 'Swipe à direita', swipe_up: 'Swipe para cima',
  swipe_down: 'Swipe para baixo', pose: 'Pose personalizada', motion: 'Movimento personalizado',
};
export const actions: Record<ActionType, string> = {
  none: 'Somente reconhecer', shortcut: 'Atalho de teclado', pointer: 'Mover cursor',
  drag_window: 'Segurar e mover janela', drag_mouse: 'Arrastar com botão esquerdo',
  scroll: 'Rolar verticalmente', click: 'Clique esquerdo', right_click: 'Clique direito', double_click: 'Clique duplo',
};
export const isContinuous = (type: ActionType) => ['pointer', 'drag_window', 'drag_mouse', 'scroll'].includes(type);
