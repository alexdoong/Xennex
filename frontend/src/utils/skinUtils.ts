import type { SkinConfig } from '../webview';

export interface BorderStyleResult {
  color: string;
  width: string;
  border: string;
}

export const computeBorder = (color?: string, opacity?: number, width?: number): BorderStyleResult => {
  const rawColor = color || '#ffffff';
  const op = opacity ?? 0.25;
  const w = width ?? 1;
  let finalColor = rawColor;

  if (rawColor.startsWith('#')) {
    const hex = rawColor.replace('#', '');
    const r = parseInt(hex.substring(0, 2) || 'ff', 16);
    const g = parseInt(hex.substring(2, 4) || 'ff', 16);
    const b = parseInt(hex.substring(4, 6) || 'ff', 16);
    finalColor = `rgba(${r}, ${g}, ${b}, ${op})`;
  } else if (rawColor.startsWith('rgba')) {
    finalColor = rawColor.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, `rgba($1,$2,$3, ${op})`);
  } else if (rawColor.startsWith('hsl')) {
    finalColor = rawColor.replace('hsl', 'hsla').replace(')', `, ${op})`);
  }

  return { color: finalColor, width: `${w}px`, border: `${w}px solid ${finalColor}` };
};

export const normalizeSkinConfig = (cfg: any): SkinConfig => {
  if (!cfg) return {} as SkinConfig;
  return {
    name: cfg.name ?? cfg.Name ?? 'default',
    backgroundType: cfg.backgroundType ?? cfg.BackgroundType ?? 'image',
    backgroundUrl: cfg.backgroundUrl ?? cfg.BackgroundUrl ?? '',
    backgroundColor: cfg.backgroundColor ?? cfg.BackgroundColor ?? '#0f131a',
    backgroundOpacity: cfg.backgroundOpacity ?? cfg.BackgroundOpacity ?? 1,
    backgroundBlur: cfg.backgroundBlur ?? cfg.BackgroundBlur ?? 0,
    sidebarImage: cfg.sidebarImage ?? cfg.SidebarImage ?? '',
    sidebarColor: cfg.sidebarColor ?? cfg.SidebarColor ?? 'rgba(15, 19, 26, 0.95)',
    titlebarImage: cfg.titlebarImage ?? cfg.TitlebarImage ?? '',
    titlebarColor: cfg.titlebarColor ?? cfg.TitlebarColor ?? 'rgba(15, 19, 26, 0.95)',
    primaryColor: cfg.primaryColor ?? cfg.PrimaryColor ?? 'hsl(260, 100%, 65%)',
    primaryHover: cfg.primaryHover ?? cfg.PrimaryHover ?? 'hsl(260, 100%, 75%)',
    textColor: cfg.textColor ?? cfg.TextColor ?? 'hsl(220, 10%, 95%)',
    borderColor: cfg.borderColor ?? cfg.BorderColor ?? 'rgba(255, 255, 255, 0.25)',
    borderOpacity: cfg.borderOpacity ?? cfg.BorderOpacity ?? 0.25,
    borderWidth: cfg.borderWidth ?? cfg.BorderWidth ?? 1,
  };
};
