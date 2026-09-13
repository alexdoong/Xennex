import type { PeerJSOption } from 'peerjs';

// Optional overrides are public build configuration. Never put a private TURN API key here.
export function peerOptions(): PeerJSOption {
  let iceServers: RTCIceServer[] = [
    { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] },
  ];
  const configured = import.meta.env.VITE_ICE_SERVERS;
  if (configured) {
    try {
      const parsed: unknown = JSON.parse(configured);
      if (!Array.isArray(parsed) || !parsed.every(server => server && typeof server === 'object' &&
        ('urls' in server) && (typeof server.urls === 'string' || Array.isArray(server.urls)))) throw new Error('Formato inválido');
      iceServers = parsed as RTCIceServer[];
    } catch (error) { console.error('[Stream] VITE_ICE_SERVERS inválido:', error); }
  }
  const host = import.meta.env.VITE_PEER_HOST;
  return {
    ...(host ? { host, port: Number(import.meta.env.VITE_PEER_PORT || 443),
      path: import.meta.env.VITE_PEER_PATH || '/', secure: import.meta.env.VITE_PEER_SECURE !== 'false' } : {}),
    config: { iceServers }, debug: 1,
  };
}
export const HAS_TURN = !!import.meta.env.VITE_ICE_SERVERS?.includes('turn:') || !!import.meta.env.VITE_ICE_SERVERS?.includes('turns:');
