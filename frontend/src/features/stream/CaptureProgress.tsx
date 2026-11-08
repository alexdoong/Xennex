import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { CAPTURE_PHASE_LABELS, type CapturePhase } from './captureStartup';

export default function CaptureProgress({ phase, cancel }: { phase: CapturePhase; cancel: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  return <div className="room-capture-progress" role="status" aria-live="polite" aria-busy="true">
    <LoaderCircle size={20} className="room-capture-spinner" aria-hidden="true"/>
    <div><strong>{phase === 'stopping' ? 'Encerrando captura' : 'Preparando transmissão'}</strong>
      <p>{CAPTURE_PHASE_LABELS[phase]} {seconds > 0 && <span>{seconds}s</span>}</p>
      {seconds >= 10 && phase !== 'stopping' && <small>Está demorando. Confira a fonte, a permissão e se a janela está visível; você pode cancelar e tentar novamente.</small>}
    </div>
    <button type="button" onClick={cancel} disabled={phase === 'stopping'}>{phase === 'stopping' ? 'Aguarde a limpeza…' : 'Cancelar captura'}</button>
  </div>;
}
