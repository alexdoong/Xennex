import { useEffect, useState } from 'react';
import { CODECS, CODEC_LABELS, codecMode, codecOrder, probeCodecs, type CodecReport } from './streamCapabilities';
import type { Quality } from './quality';

export default function StreamCompatibilityOptions({ quality, onChange, active, disabled, direction = 'encode' }: {
  quality: Quality; onChange(value: Quality): void; active: boolean; disabled: boolean; direction?: CodecReport['direction'];
}) {
  const [report, setReport] = useState<CodecReport>();
  const { resolution, fps, uploadMbps } = quality;
  useEffect(() => {
    if (!active) return;
    let current = true;
    setReport(undefined);
    const timer = setTimeout(() => { void probeCodecs({ resolution, fps, uploadMbps, preference: 'motion' }, direction).then(value => { if (current) setReport(value); }); }, 250);
    return () => { current = false; clearTimeout(timer); };
  }, [active, resolution, fps, uploadMbps, direction]);
  const mode = codecMode(quality.codec), suggested = codecOrder('auto', direction, report)[0];
  const label = direction === 'encode' ? 'Formato do vídeo' : 'Formato para assistir';
  return <div className="room-compatibility-options">
    <label>{label}<select aria-label={label} value={mode} disabled={disabled} onChange={event => onChange({ ...quality, codec: codecMode(event.target.value) })}>
      <option value="auto">Automático · recomendado</option>
      <option value="compatibility">Priorizar compatibilidade</option>
      {CODECS.map(codec => <option key={codec} value={codec} disabled={!report?.codecs.some(c => c.codec === codec && c.advertised)}>Preferir {CODEC_LABELS[codec]}</option>)}
    </select></label>
    <p className="room-helper">{direction === 'encode' ? 'Cada espectador negocia um formato compatível. As preferências mantêm alternativas para dispositivos com menos recursos.' : 'Esta escolha vale somente neste dispositivo. Ao mudar, os vídeos que você assiste serão reconectados.'}</p>
    <div aria-live="polite">
      {!report ? <small>Verificando recursos do navegador…</small> : <>
        <small>{report.codecs.length ? `Disponíveis: ${report.codecs.map(c => CODEC_LABELS[c.codec]).join(', ')}.` : 'O navegador não informa seus codecs. A negociação padrão continua disponível.'}</small>
        {report.codecs.length > 0 && <small>Perfil consultado: {report.width} × {report.height}, até {report.fps} FPS.</small>}
        {suggested && <small>Preferência automática sugerida: {CODEC_LABELS[suggested]}.</small>}
        {report.codecs.length > 0 && <small>{report.codecs.some(c => c.powerEfficient !== undefined) ? 'Eficiência estimada pelo navegador; o resultado depende também do espectador, da carga e da conexão.' : 'Aceleração e fluidez não confirmadas. Automático mantém as escolhas padrão do navegador.'}</small>}
      </>}
    </div>
  </div>;
}
