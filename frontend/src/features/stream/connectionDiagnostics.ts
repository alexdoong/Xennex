import type { DataConnection } from 'peerjs';
import type { EntryObservation } from './entryDiagnostics';

/** Log transport states and candidate categories only: never SDP, IPs or TURN credentials. */
export function observeRoomConnection(connection: DataConnection, current: () => boolean, trace: (message: string) => void, observe: (value: EntryObservation) => void = () => {}) {
  let peer: RTCPeerConnection | undefined;
  let last = '';
  let gathered = false;
  let closed = false, routeBusy = false, routeReported = false;
  const counts = { host: 0, srflx: 0, prflx: 0, relay: 0 };
  const errors = new Set<number>();
  const selectedRoute = () => {
    if (closed || !current() || !peer || routeBusy || routeReported || peer.connectionState !== 'connected' || typeof peer.getStats !== 'function') return;
    routeBusy = true;
    void peer.getStats().then(stats => {
      if (closed || !current()) return;
      stats.forEach(item => {
        if (routeReported || item.type !== 'candidate-pair' || item.state !== 'succeeded' || !item.nominated) return;
        const local = stats.get(item.localCandidateId)?.candidateType;
        const remote = stats.get(item.remoteCandidateId)?.candidateType;
        if (!local || !remote) return;
        routeReported = true;
        observe({ route: local === 'relay' || remote === 'relay' ? 'relay' : 'direct' });
        trace(local === 'relay' || remote === 'relay' ? 'Rota da entrada: retransmissão TURN.' : 'Rota da entrada: direta entre participantes.');
      });
    }).catch(() => {}).finally(() => { routeBusy = false; });
  };
  const report = () => {
    if (closed || !current() || !peer) return;
    observe({ ice: peer.iceConnectionState, connection: peer.connectionState, gathering: peer.iceGatheringState,
      host: counts.host, public: counts.srflx + counts.prflx, relay: counts.relay });
    const state = `Entrada na sala: ICE ${peer.iceConnectionState} · transporte ${peer.connectionState} · coleta ${peer.iceGatheringState}`;
    if (last !== state) { last = state; trace(state); }
    if (peer.iceGatheringState === 'complete' && !gathered) {
      gathered = true;
      trace(`Rotas locais observadas: diretas ${counts.host} · públicas ${counts.srflx + counts.prflx} · retransmissão ${counts.relay}. Observar uma rota não comprova conexão.`);
    }
    selectedRoute();
  };
  const candidate = (event: RTCPeerConnectionIceEvent) => {
    if (!current()) return;
    const type = event.candidate?.type;
    if (type && type in counts) counts[type]++;
  };
  const error = (event: RTCPeerConnectionIceErrorEvent) => {
    if (!current() || errors.has(event.errorCode)) return;
    errors.add(event.errorCode);
    observe({ errorCode: event.errorCode });
    trace(`Consulta STUN/TURN retornou código ${event.errorCode}; isso não comprova falha de todos os servidores.`);
  };
  const bind = () => {
    if (!current()) return;
    if (!peer && connection.peerConnection) {
      peer = connection.peerConnection;
      peer.addEventListener('iceconnectionstatechange', report);
      peer.addEventListener('connectionstatechange', report);
      peer.addEventListener('icegatheringstatechange', report);
      peer.addEventListener('icecandidate', candidate);
      peer.addEventListener('icecandidateerror', error);
    }
    report();
  };
  const stop = () => {
    closed = true;
    connection.off('iceStateChanged', bind);
    peer?.removeEventListener('iceconnectionstatechange', report);
    peer?.removeEventListener('connectionstatechange', report);
    peer?.removeEventListener('icegatheringstatechange', report);
    peer?.removeEventListener('icecandidate', candidate);
    peer?.removeEventListener('icecandidateerror', error);
  };
  connection.on('iceStateChanged', bind);
  connection.on('close', stop);
  bind();
}
