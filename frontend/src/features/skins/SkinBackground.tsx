import { useEffect, useRef, type CSSProperties } from 'react';
import type { SkinConfig } from '../../webview';
import { cssImage } from '../../utils/skinUtils';

export default function SkinBackground({ config }: { config: SkinConfig | null }) {
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    if (config?.pauseBackgroundVideo || config?.reducedMotion) element.pause();
    else void element.play().catch(() => { /* A failed or unsupported URL leaves the base color visible. */ });
  }, [config?.pauseBackgroundVideo, config?.reducedMotion, config?.backgroundUrl, config?.backgroundType]);
  if (!config) return null;
  const style: CSSProperties = {
    opacity: config.backgroundOpacity,
    filter: `blur(${config.backgroundBlur}px) brightness(${config.backgroundBrightness}%) saturate(${config.backgroundSaturation}%)`,
    objectFit: config.backgroundFit as CSSProperties['objectFit'],
    objectPosition: `${config.backgroundPositionX}% ${config.backgroundPositionY}%`,
  };
  return <>
    {config.backgroundType === 'video' && config.backgroundUrl && <video ref={video} key={config.backgroundUrl} className="main-window-bg-video" src={config.backgroundUrl} muted loop playsInline style={style}/>}
    {config.backgroundType === 'image' && config.backgroundUrl && <div className="main-window-bg-image" style={{ ...style, backgroundImage: cssImage(config.backgroundUrl), backgroundRepeat:'no-repeat', backgroundSize:config.backgroundFit === 'fill' ? '100% 100%' : config.backgroundFit, backgroundPosition:style.objectPosition }}/>}
    {config.backgroundType === 'gradient' && <div className="main-window-bg-image" style={{ ...style, backgroundImage:`linear-gradient(${config.gradientAngle}deg, ${config.backgroundColor}, ${config.gradientColor})` }}/>}
    <div className="skin-background-overlay" style={{ background:config.overlayColor,opacity:config.overlayOpacity }}/>
  </>;
}
