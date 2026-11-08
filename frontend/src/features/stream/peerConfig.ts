import type { PeerJSOption } from 'peerjs';
import { parseIceConfig } from './iceConfig';

const ice = parseIceConfig(import.meta.env.VITE_ICE_SERVERS);
if (ice.invalid) console.error('[Stream] Configuração ICE inválida; usando STUN padrão, sem TURN.');

// Optional overrides are public build configuration. Never put a private TURN API key here.
export function peerOptions(): PeerJSOption {
  const host = import.meta.env.VITE_PEER_HOST;
  return {
    ...(host ? { host, port: Number(import.meta.env.VITE_PEER_PORT || 443),
      path: import.meta.env.VITE_PEER_PATH || '/', secure: import.meta.env.VITE_PEER_SECURE !== 'false' } : {}),
    config: { iceServers: ice.iceServers }, debug: 1,
  };
}
export const HAS_TURN = ice.hasTurn;
