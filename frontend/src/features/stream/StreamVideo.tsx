import { useEffect, useRef, useState } from 'react';
import { Maximize, Minimize2, Volume2, VolumeX, PictureInPicture2, Scan, Pin } from 'lucide-react';
import type { VideoReading } from './streamStats';
import { QUALITY_PRESETS, type Quality } from './quality';
interface Props { stream: MediaStream; name: string; local?: boolean; audible: boolean; focused: boolean;
  reading?: VideoReading; quality?: Quality; onAudio(): void; onFocus(): void }
export default function StreamVideo({ stream, name, local, audible, focused, reading, quality, onAudio, onFocus }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const panel = useRef<HTMLElement>(null);
  const [volume, setVolume] = useState(1);
  const [cover, setCover] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [dimensions, setDimensions] = useState('');
  const [fps, setFps] = useState<number | undefined>(undefined);
  useEffect(() => {
    const element = video.current; if (!element) return;
    element.srcObject = stream;
    setDimensions(''); setBlocked(false);
    void element.play().catch(() => setBlocked(true));
    setFps(undefined);
    let presented: number | undefined;
    let callback = 0;
    let disposed = false;
    const frame: VideoFrameRequestCallback = (_now, metadata) => {
      if (disposed) return;
      presented = metadata.presentedFrames;
      callback = element.requestVideoFrameCallback(frame);
    };
    if (element.requestVideoFrameCallback) callback = element.requestVideoFrameCallback(frame);
    let frames: number | undefined;
    let timestamp = performance.now();
    const timer = setInterval(() => {
      const current = presented ?? element.getVideoPlaybackQuality?.().totalVideoFrames;
      const now = performance.now();
      if (document.hidden) { frames = undefined; setFps(undefined); timestamp = now; return; }
      if (current !== undefined && frames !== undefined && current >= frames && now > timestamp && (presented !== undefined || current > 0)) {
        setFps(Math.round((current - frames) * 1000 / (now - timestamp)));
      } else setFps(undefined);
      frames = current; timestamp = now;
    }, 2000);
    const update = () => setDimensions(element.videoWidth ? `${element.videoWidth} × ${element.videoHeight}` : '');
    update();
    element.addEventListener('resize', update); element.addEventListener('loadedmetadata', update);
    return () => { disposed = true; clearInterval(timer); if (callback) element.cancelVideoFrameCallback(callback); element.removeEventListener('resize', update); element.removeEventListener('loadedmetadata', update); element.srcObject = null; };
  }, [stream]);
  useEffect(() => {
    const element = video.current; if (!element) return;
    element.muted = !!local || !audible; element.volume = volume;
    void element.play().then(() => setBlocked(false)).catch(() => setBlocked(true));
  }, [audible, local, volume]);
  const play = () => { void video.current?.play().then(() => setBlocked(false)).catch(() => setBlocked(true)); };
  const fullscreen = async () => {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await panel.current?.requestFullscreen(); }
    catch (error) { console.warn('[Viewer] Tela cheia indisponível:', error); }
  };
  const pip = async () => {
    try { if (document.pictureInPictureElement) await document.exitPictureInPicture(); else await video.current?.requestPictureInPicture(); }
    catch (error) { console.warn('[Viewer] Picture-in-picture indisponível:', error); }
  };
  const measuredFps = local ? fps : reading?.arrivalFps ?? reading?.fps ?? fps;
  const sourceSettings = local ? stream.getVideoTracks()[0]?.getSettings() : undefined;
  const actualSize = reading?.width && reading.height ? `${reading.width} × ${reading.height}` : dimensions;
  const sourceLabel = local ? 'Prévia' : reading?.arrivalFps !== undefined ? 'Recebendo' : reading?.fps !== undefined ? 'Decodificando' : 'Exibindo';
  const target = quality ? `Alvo: ${QUALITY_PRESETS[quality.resolution].label} · ${quality.fps || 'Auto'} FPS. ` : '';
  const sourceInfo = sourceSettings?.width ? `Captura: ${sourceSettings.width} × ${sourceSettings.height}${sourceSettings.frameRate ? ` · limite ${Math.round(sourceSettings.frameRate)} FPS` : ''}. ` : '';
  return <article className={`room-video ${focused ? 'room-video-focused' : ''}`} ref={panel}
    onDoubleClick={event => { if (!(event.target as HTMLElement).closest('button,input')) onFocus(); }}>
    <video ref={video} autoPlay playsInline muted={!!local || !audible} style={{ objectFit: cover ? 'cover' : 'contain' }} />
    <div className="room-video-top"><span><i />{name}{local ? ' · você' : ''}</span><small className="room-video-metrics"
      title={`${target}${sourceInfo}${sourceLabel}: medidas reais nesta ponta; o limite da captura não garante FPS entregues. Duplo clique no vídeo para destacar.`}>
      {sourceLabel} · {actualSize || 'Aguardando imagem'} · {measuredFps === undefined ? 'FPS indisponível' : `${Math.round(measuredFps)} FPS`}
      {reading?.mbps !== undefined && ` · ${reading.mbps.toFixed(1)} Mbps`}
      {!local && reading?.arrivalFps !== undefined && reading.fps !== undefined && Math.abs(reading.arrivalFps - reading.fps) >= 5 && ` · decode ${Math.round(reading.fps)} FPS`}
    </small></div>
    {blocked && <button className="room-play-overlay" onClick={play}>Clique para reproduzir</button>}
    <div className="room-video-controls">
      {!local && <><button title={audible ? 'Silenciar' : 'Ouvir esta transmissão'} aria-label={audible ? 'Silenciar' : 'Ouvir esta transmissão'} onClick={onAudio}>{audible ? <Volume2 size={17}/> : <VolumeX size={17}/>}</button>
        <input aria-label="Volume" type="range" min="0" max="1" step="0.05" value={volume} onChange={event => setVolume(Number(event.target.value))}/></>}
      {local && <small>Prévia sem retorno de áudio</small>}
      <span className="room-spacer"/>
      <button title={focused ? 'Voltar à grade' : 'Destacar transmissão'} aria-label="Destacar transmissão" onClick={onFocus}>{focused ? <Minimize2 size={17}/> : <Pin size={17}/>}</button>
      <button title="Ajustar preenchimento" aria-label="Ajustar preenchimento" onClick={() => setCover(!cover)}><Scan size={17}/></button>
      {document.pictureInPictureEnabled && <button title="Picture-in-picture" aria-label="Picture-in-picture" onClick={() => void pip()}><PictureInPicture2 size={17}/></button>}
      <button title="Tela cheia" aria-label="Tela cheia" onClick={() => void fullscreen()}><Maximize size={17}/></button>
    </div>
  </article>;
}
