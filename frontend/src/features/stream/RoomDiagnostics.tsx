import { useEffect, useRef, useState } from 'react';
import type { RoomClient } from './RoomClient';
import { bitrateBudget, qualityWarning } from './quality';
import { DEFAULT_QUALITY } from './quality';
import { codecMode, type CodecMode } from './streamCapabilities';
import StreamCompatibilityOptions from './StreamCompatibilityOptions';
import { sampleRtp, type RtpSample, type VideoReading } from './streamStats';
import type { SessionBenchmark } from './sessionBenchmark';
import RoomBenchmark from './RoomBenchmark';
export default function RoomDiagnostics({ client, onReadings }: { client: RoomClient; onReadings(readings: Record<string, VideoReading>): void }) {
  const [summary, setSummary] = useState('Aguardando conexão de mídia');
  const [details, setDetails] = useState<string[]>([]);
  const [receiveMode, setReceiveMode] = useState<CodecMode>(client.receivingCodec);
  const benchmark = useRef<SessionBenchmark | undefined>(undefined);
  useEffect(() => {
    try { const mode = codecMode(localStorage.getItem('xennex_receive_codec')); setReceiveMode(mode); client.setReceivingCodec(mode); }
    catch { /* Storage is optional; in-memory automatic mode remains available. */ }
  }, [client]);
  useEffect(() => {
    let disposed = false; let busy = false;
    const previous = new WeakMap<RTCPeerConnection, Map<string, RtpSample>>();
    const timer = setInterval(async () => {
      if (busy) return; busy = true;
      let out = 0; let incoming = 0; let audioOut = 0; let audioIn = 0; let rtt = 0; let relay = false; let links = 0;
      const lines: string[] = [];
      const readings: Record<string, VideoReading> = {};
      try {
        const connections = client.connectionDetails();
        const copies = connections.filter(item => item.direction === 'outgoing').length;
        const uploadMbps = Math.min(...connections.flatMap(item => item.quality ? [item.quality.uploadMbps] : []));
        for (const { id, direction, title, quality, connection: pc } of connections) {
          if (disposed) return;
          if (pc.connectionState !== 'connected') continue;
          links++;
          const adjustment = qualityWarning(pc);
          if (adjustment) lines.push(`${title}: ${adjustment}`);
          const stats = await pc.getStats();
          const history = previous.get(pc) || new Map();
          previous.set(pc, history);
          stats.forEach(report => {
            const kind = report.kind || report.mediaType;
            const expected = direction === 'outgoing' ? 'outbound-rtp' : 'inbound-rtp';
            if (report.type === expected && ['video', 'audio'].includes(kind) && !report.isRemote) {
              const { sample, reading } = sampleRtp(report, history.get(report.id));
              reading.activity = document.hidden ? 'hidden' : document.hasFocus() ? 'focused' : 'unfocused';
              const { fps } = reading;
              const mbps = reading.mbps || 0;
              history.set(report.id, sample);
              if (kind === 'audio') {
                if (direction === 'outgoing') audioOut += mbps; else audioIn += mbps;
                lines.push(`${direction === 'outgoing' ? 'Enviando' : 'Recebendo'} áudio · ${title}: ${mbps.toFixed(2)} Mbps`);
                return;
              }
              if (direction === 'incoming') readings[id] = reading;
              if (direction === 'outgoing') out += mbps; else incoming += mbps;
              const size = report.frameWidth && report.frameHeight ? `${report.frameWidth} × ${report.frameHeight}` : 'resolução indisponível';
              const limitation = report.qualityLimitationReason === 'bandwidth' ? ' · limitado pela rede'
                : report.qualityLimitationReason === 'cpu' ? ' · limitado pelo processamento'
                : report.qualityLimitationReason === 'other' ? ' · limitação do encoder' : '';
              const target = quality ? ` · alvo ${quality.resolution === 'source' ? 'original' : quality.resolution}/${quality.fps || 'auto'} FPS` : '';
              const budget = quality ? ` · teto por cópia ${(bitrateBudget({ ...quality, uploadMbps }, copies) / 1000000).toFixed(1)} Mbps (${copies} cópias)` : '';
              const measuredFps = direction === 'incoming' ? reading.arrivalFps ?? fps : fps;
              const verb = direction === 'outgoing' ? 'Enviando' : reading.arrivalFps !== undefined ? 'Recebendo' : 'Decodificando';
              lines.push(`${verb} ${title}: ${size} · ${measuredFps === undefined ? '—' : Math.round(measuredFps)} FPS · ${reading.mbps === undefined ? '—' : mbps.toFixed(1)} Mbps${target}${budget}${limitation}`);
              const codec = stats.get(report.codecId);
              benchmark.current?.record(pc, direction, reading, codec?.mimeType);
              const parts: string[] = [];
              if (direction === 'incoming' && reading.arrivalFps !== undefined) parts.push(`chegada ${reading.arrivalFps.toFixed(1)} FPS · decode ${fps === undefined ? '—' : fps.toFixed(1)} FPS`);
              parts.push(reading.activity === 'hidden' ? 'aba oculta' : reading.activity === 'unfocused' ? 'aba sem foco' : 'aba focada');
              if (typeof codec?.mimeType === 'string') parts.push(`codec ${codec.mimeType.slice(0, 60)}`);
              const h = reading.health;
              if (h?.encodeMs !== undefined) parts.push(`codificar ${h.encodeMs.toFixed(1)} ms/quadro`);
              if (h?.decodeMs !== undefined) parts.push(`decodificar ${h.decodeMs.toFixed(1)} ms/quadro`);
              if (h?.jitterBufferMs !== undefined) parts.push(`buffer de recepção ${h.jitterBufferMs.toFixed(1)} ms`);
              if (h?.lossPercent !== undefined) parts.push(`perda ${h.lossPercent.toFixed(1)}%`);
              if (h?.droppedFrames !== undefined) parts.push(`descartados +${h.droppedFrames}`);
              if (h?.nacks !== undefined) parts.push(`reenvios solicitados +${h.nacks}`);
              if (h?.plis !== undefined) parts.push(`quadros-chave solicitados +${h.plis}`);
              if (h?.freezes !== undefined) parts.push(`congelamentos +${h.freezes}`);
              if (parts.length) lines.push(`${title}: ${parts.join(' · ')}`);
            }
            if (report.type === 'candidate-pair' && report.state === 'succeeded' && report.nominated) {
              rtt = Math.max(rtt, (report.currentRoundTripTime || 0) * 1000);
              relay ||= stats.get(report.localCandidateId)?.candidateType === 'relay' || stats.get(report.remoteCandidateId)?.candidateType === 'relay';
            }
          });
        }
        if (!disposed) {
          setDetails(lines);
          onReadings(readings);
          setSummary(links ? `Vídeo ↑ ${out.toFixed(1)} · ↓ ${incoming.toFixed(1)} Mbps · Áudio ↑ ${audioOut.toFixed(2)} · ↓ ${audioIn.toFixed(2)} Mbps · ${Math.round(rtt)} ms · ${relay ? 'retransmissão TURN' : 'conexão direta'}` : 'Aguardando conexão de mídia');
        }
      } catch (error) {
        if (!disposed) { onReadings({}); setDetails([]); setSummary('Medição de qualidade temporariamente indisponível'); }
        console.debug('[Room] Estatísticas indisponíveis:', error);
      }
      finally { busy = false; }
    }, 2000);
    return () => { disposed = true; clearInterval(timer); };
  }, [client, onReadings]);
  return <div className="room-diagnostics">{summary}
    <RoomBenchmark current={benchmark}/>
    <details><summary>Compatibilidade deste dispositivo</summary><StreamCompatibilityOptions direction="decode" quality={{ ...DEFAULT_QUALITY, codec: receiveMode }} active={true} disabled={false} onChange={value => {
      const mode = codecMode(value.codec); setReceiveMode(mode); client.setReceivingCodec(mode);
      try { localStorage.setItem('xennex_receive_codec', mode); } catch { /* Optional local preference. */ }
    }}/></details>
    {details.length > 0 && <details><summary>Qualidade real por conexão</summary>
    {details.map((line, index) => <p key={index}>{line}</p>)}
    <small>Valores RTP medidos nesta ponta; não representam todo o tráfego de rede. Tempos por quadro são médias no intervalo, e contagens “+” são diferenças entre amostras. Campos ausentes ficam indisponíveis; codec não comprova aceleração por hardware. Uma cópia é enviada por espectador; cenas paradas podem produzir menos FPS.</small>
  </details>}</div>;
}
