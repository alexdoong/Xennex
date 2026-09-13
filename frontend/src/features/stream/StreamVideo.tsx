import { useEffect, useRef, useState } from 'react';
import { Maximize, Minimize2, Volume2, VolumeX, PictureInPicture2, Scan, Pin } from 'lucide-react';
interface Props { stream: MediaStream; name: string; local?: boolean; audible: boolean; focused: boolean;
  onAudio(): void; onFocus(): void }
export default function StreamVideo({ stream, name, local, audible, focused, onAudio, onFocus }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const panel = useRef<HTMLElement>(null);
  const [volume, setVolume] = useState(1);
  const [cover, setCover] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [dimensions, setDimensions] = useState('');
  useEffect(() => {
    const element = video.current; if (!element) return;
    element.srcObject = stream;
    void element.play().catch(() => setBlocked(true));
    const update = () => setDimensions(`${element.videoWidth} × ${element.videoHeight}`);
    element.addEventListener('resize', update); element.addEventListener('loadedmetadata', update);
    return () => { element.removeEventListener('resize', update); element.removeEventListener('loadedmetadata', update); element.srcObject = null; };
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
  return <article className={`room-video ${focused ? 'room-video-focused' : ''}`} ref={panel}>
    <video ref={video} autoPlay playsInline muted={!!local || !audible} style={{ objectFit: cover ? 'cover' : 'contain' }} />
    <div className="room-video-top"><span><i />{name}{local ? ' · você' : ''}</span><small>{dimensions}</small></div>
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
