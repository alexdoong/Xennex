import { useEffect, useState } from 'react';
import type { RoomClient } from './RoomClient';
export default function RoomDiagnostics({ client }: { client: RoomClient }) {
  const [summary, setSummary] = useState('Aguardando conexão de mídia');
  useEffect(() => {
    let disposed = false; let busy = false;
    const previous = new Map<string, { bytes: number; timestamp: number }>();
    const timer = setInterval(async () => {
      if (busy) return; busy = true;
      let out = 0; let incoming = 0; let rtt = 0; let relay = false; let links = 0;
      try {
        const connections = client.connections();
        for (const [direction, list] of Object.entries(connections)) {
          for (const [index, pc] of list.entries()) {
            if (pc.connectionState !== 'connected') continue;
            links++;
            const stats = await pc.getStats();
            stats.forEach(report => {
              if ((report.type === 'outbound-rtp' || report.type === 'inbound-rtp') && report.kind === 'video') {
                const bytes = report.bytesSent ?? report.bytesReceived;
                const key = `${direction}:${index}:${report.id}`;
                const last = previous.get(key);
                if (last && report.timestamp > last.timestamp && bytes >= last.bytes) {
                  const mbps = (bytes - last.bytes) * 8 / (report.timestamp - last.timestamp) / 1000;
                  if (direction === 'outgoing') out += mbps; else incoming += mbps;
                }
                previous.set(key, { bytes, timestamp: report.timestamp });
              }
              if (report.type === 'candidate-pair' && report.state === 'succeeded' && report.nominated) {
                rtt = Math.max(rtt, (report.currentRoundTripTime || 0) * 1000);
                relay ||= stats.get(report.localCandidateId)?.candidateType === 'relay' || stats.get(report.remoteCandidateId)?.candidateType === 'relay';
              }
            });
          }
        }
        if (!disposed) setSummary(links ? `↑ ${out.toFixed(1)} Mbps · ↓ ${incoming.toFixed(1)} Mbps · ${Math.round(rtt)} ms · ${relay ? 'retransmissão TURN' : 'conexão direta'}` : 'Aguardando conexão de mídia');
      } catch (error) { console.debug('[Room] Estatísticas indisponíveis:', error); }
      finally { busy = false; }
    }, 2000);
    return () => { disposed = true; clearInterval(timer); };
  }, [client]);
  return <div className="room-diagnostics">{summary}</div>;
}
