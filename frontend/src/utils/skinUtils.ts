import type { SkinConfig } from '../webview';
import { SKIN_FIELDS } from '../features/skins/skinFields';
import { DEFAULT_SKIN } from '../features/skins/skinDefaults';
import { CUSTOMIZABLE_TABS } from '../layout/navigation';

export const skinColor = (value: string, fallback = '#ffffff') =>
  typeof value === 'string' && !/[;{}<>]|var\(/i.test(value) && CSS.supports('color', value) ? value : fallback;

export function colorWithOpacity(value: string, opacity: number) {
  const context = document.createElement('canvas').getContext('2d');
  if (!context) return value;
  context.fillStyle = skinColor(value); context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, opacity))})`;
}
export function skinColorHex(value: string) {
  const channels = colorWithOpacity(value, 1).match(/^rgba\((\d+), (\d+), (\d+),/);
  return channels ? '#' + channels.slice(1, 4).map(part => Number(part).toString(16).padStart(2, '0')).join('') : '#ffffff';
}
export const computeBorder = (color = '#ffffff', opacity = .25, width = 1) => {
  const result = colorWithOpacity(color, opacity);
  return { color: result, width: `${width}px`, border: `${width}px solid ${result}` };
};
export const skinUrl = (value: string) => {
  if (!value) return '';
  try { const url = new URL(value, 'https://appassets/'); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
};
export const cssImage = (value: string) => skinUrl(value) ? `url(${JSON.stringify(skinUrl(value))})` : 'none';

export function normalizeSkinConfig(input: unknown): SkinConfig {
  const raw = input && typeof input === 'object' ? input as Record<string, unknown> : {};
  const result: Record<string, unknown> = { ...raw };
  for (const [key, fallback] of Object.entries(DEFAULT_SKIN)) {
    const pascal = key[0].toUpperCase() + key.slice(1);
    const value = raw[key] ?? raw[pascal] ?? fallback;
    result[key] = typeof value === typeof fallback && (typeof value !== 'number' || Number.isFinite(value)) ? value : fallback;
    delete result[pascal];
    if (key.endsWith('Color') || key === 'primaryHover') result[key] = skinColor(String(result[key]), String(fallback));
  }
  for (const field of SKIN_FIELDS) if (field.kind === 'range') result[field.key] = Math.max(field.min!, Math.min(field.max!, Number(result[field.key])));
  const cfg = result as unknown as SkinConfig;
  if (!['cover','contain','fill'].includes(cfg.backgroundFit)) cfg.backgroundFit = 'cover';
  if (!['system','segoe','mono'].includes(cfg.fontFamily)) cfg.fontFamily = 'system';
  if (!['left','right','bottom'].includes(cfg.navigationPlacement)) cfg.navigationPlacement = 'left';
  if (!['left','center','right'].includes(cfg.controlsPlacement)) cfg.controlsPlacement = 'right';
  if (!['floating','filled'].includes(cfg.windowPresentation)) cfg.windowPresentation = 'floating';
  if (!['glass','liquid','solid','terminal','ornate'].includes(cfg.surfaceStyle)) cfg.surfaceStyle = 'glass';
  const navigationIds: string[] = CUSTOMIZABLE_TABS.map(tab => tab.id);
  const ordered = Array.isArray(cfg.navigationOrder) ? cfg.navigationOrder.filter((id): id is string => typeof id === 'string' && navigationIds.includes(id)) : [];
  cfg.navigationOrder = [...new Set([...ordered, ...navigationIds])];
  const sectionIds = ['behavior','layout','skins','about'];
  const sectionOrder = Array.isArray(cfg.settingsSectionOrder) ? cfg.settingsSectionOrder.filter((id): id is string => typeof id === 'string' && sectionIds.includes(id)) : [];
  cfg.settingsSectionOrder = [...new Set([...sectionOrder, ...sectionIds])];
  cfg.settingsColumns = Math.max(1, Math.min(2, Number(cfg.settingsColumns) || 1));
  if (!['image', 'video', 'color', 'gradient'].includes(cfg.backgroundType)) cfg.backgroundType = 'color';
  for (const key of ['backgroundUrl', 'sidebarImage', 'titlebarImage'] as const) cfg[key] = skinUrl(cfg[key]);
  return cfg;
}

export function applySkinVariables(cfg: SkinConfig) {
  const root = document.documentElement;
  const border = computeBorder(cfg.borderColor, cfg.borderOpacity, cfg.borderWidth);
  const variables: Record<string, string> = {
    primary: cfg.primaryColor, 'primary-hover': cfg.primaryHover, 'primary-glow': colorWithOpacity(cfg.primaryColor, .4),
    'text-primary': cfg.textColor, 'text-secondary': cfg.secondaryTextColor, 'button-text': cfg.buttonTextColor,
    'border-color': border.color, 'border-width': border.width, border: border.border,
    'panel-background': colorWithOpacity(cfg.panelColor, cfg.panelOpacity), 'panel-blur': `${cfg.panelBlur}px`,
    'glass-rim': colorWithOpacity(cfg.borderColor || '#ffffff', cfg.glassHighlight * .65),
    'glass-sheen': colorWithOpacity(cfg.borderColor || '#ffffff', cfg.glassHighlight * .18),
    'glass-shade': colorWithOpacity(cfg.backgroundColor, cfg.glassHighlight * .3),
    'radius-lg': `${cfg.panelRadius}px`, 'panel-padding': `${cfg.panelPadding}px`, 'button-radius': `${cfg.buttonRadius}px`,
    'surface-shadow': `0 10px 30px rgba(0,0,0,${cfg.shadowStrength})`, 'input-background': cfg.inputColor,
    'content-scale': String(cfg.contentScale / 100), 'content-padding': `${cfg.contentPadding}px`,
    'sidebar-width': `${cfg.sidebarWidth}px`, 'sidebar-radius': `${cfg.sidebarRadius}px`, 'window-radius': `${cfg.windowRadius}px`,
    'bar-blur': `${cfg.barBlur}px`, 'scrollbar-width': `${cfg.scrollbarWidth}px`, 'scrollbar-color': cfg.scrollbarColor,
    'font-family': cfg.fontFamily === 'mono' ? 'Consolas, monospace' : cfg.fontFamily === 'segoe' ? '"Segoe UI", sans-serif' : 'Inter, system-ui, sans-serif',
    'frame-fill': skinColor(cfg.backgroundColor, '#0f131a'),
    'card-background': colorWithOpacity(cfg.cardColor, cfg.cardOpacity),
    'card-border': `1px solid ${colorWithOpacity(cfg.cardBorderColor, cfg.cardBorderOpacity)}`,
    'card-radius': `${cfg.cardRadius}px`, 'card-padding': `${cfg.cardPadding}px`, 'card-gap': `${cfg.cardGap}px`,
  };
  for (const [key, value] of Object.entries(variables)) root.style.setProperty(`--${key}`, value);
  root.dataset.reducedMotion = String(cfg.reducedMotion);
  root.dataset.navigationPlacement = cfg.navigationPlacement;
}
