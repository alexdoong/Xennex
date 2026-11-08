import { useEffect, useState } from 'react';
import { CODECS, CODEC_LABELS, codecMode, probeCodecs, type CodecReport } from './streamCapabilities';
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
  const mode = codecMode(quality.codec);
  const label = direction === 'encode' ? 'Formato do vídeo' : 'Formato para assistir';
  return <div className="room-compatibility-options">
    <label>{label}<select aria-label={label} value={mode} disabled={disabled} onChange={event => onChange({ ...quality, codec: codecMode(event.target.value) })}>
      <option value="auto">Automático · recomendado</option>
      <option value="compatibility">Priorizar compatibilidade</option>
      {CODECS.map(codec => <option key={codec} value={codec} disabled={!report?.codecs.some(c => c.codec === codec && c.advertised)}>Preferir {CODEC_LABELS[codec]}</option>)}
    </select></label>
  </div>;
}
