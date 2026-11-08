import { useEffect, useState } from 'react';
import type { LocalCapture } from './useRoom';

export default function CapturePipelineDiagnostics({ captures }: { captures: LocalCapture[] }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 3000); return () => clearInterval(timer); }, []);
  const measured = captures.filter(item => item.pipeline);
  if (!measured.length) return null;
  return <details className="room-diagnostics"><summary>Processamento da captura no app</summary>
    {measured.map(item => {
      const pipeline = item.pipeline!, m = pipeline.worker;
      return <div key={item.id}><strong>{item.title}</strong>
        <p>{m.sourceWidth} × {m.sourceHeight} → {m.outputWidth} × {m.outputHeight} · {m.scalePath === 'gpu' ? 'Redução/rotação na GPU' : m.scalePath === 'cpu' ? 'Alternativa por CPU' : 'Tamanho original'} · {(m.mappedBytes / 1048576).toFixed(1)} MiB lidos/quadro</p>
        {now - pipeline.receivedAt > 6000 ? <p>Sem amostra recente; uma imagem parada pode não produzir quadros novos.</p> : <>
          <p>{m.processedFps.toFixed(1)} quadros/s processados · pré-JPEG {m.beforeJpegMs.toFixed(1)} ms (espera/leitura GPU {m.mapMs.toFixed(1)} ms) · JPEG {m.jpegMs.toFixed(1)} ms · total médio {m.totalMs.toFixed(1)} ms · p95 {m.p95Ms.toFixed(1)} ms</p>
          {pipeline.decodeMs !== undefined && <>
            <p>{pipeline.output === 'worker-generator' ? 'Worker de vídeo' : 'WebView'} · {pipeline.decoder === 'webcodecs' ? 'WebCodecs / VideoFrame' : 'ImageBitmap compatível'}: JPEG {pipeline.decodeMs.toFixed(1)} ms (p95 {pipeline.decodeP95Ms?.toFixed(1)} ms) · {pipeline.output && pipeline.output !== 'canvas' ? `trilha de vídeo ${pipeline.submitMs?.toFixed(1)} ms` : `canvas ${pipeline.drawMs?.toFixed(1)} ms`}</p>
            <p>Espera local {pipeline.queueMs?.toFixed(1)} ms · chegada até envio à saída p95 {pipeline.ageP95Ms?.toFixed(1)} ms · {pipeline.replacedFrames ?? 0} quadros substituídos de {pipeline.receivedFrames ?? 0} recebidos nesta amostra</p>
          </>}
        </>}
      </div>;
    })}
    <small>Medições locais, anteriores ao encoder WebRTC. Chegada é o evento do socket local, não o instante da captura. A espera GPU faz parte do pré-JPEG. Canvas/trilha medem submissão, sem medir conclusão na GPU ou entrega ao espectador. FPS recebido e limitações da rede estão em “Qualidade real por conexão”.</small>
  </details>;
}
