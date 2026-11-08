const DEFAULT_ICE: RTCIceServer[] = [{ urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] }];
export function parseIceConfig(configured?: string): { iceServers: RTCIceServer[]; hasTurn: boolean; invalid: boolean } {
  if (!configured) return { iceServers: DEFAULT_ICE, hasTurn: false, invalid: false };
  try {
    const parsed: unknown = JSON.parse(configured);
    if (!Array.isArray(parsed) || !parsed.length) throw new Error('Lista inválida');
    const iceServers: RTCIceServer[] = parsed.map((server: unknown) => {
      if (!server || typeof server !== 'object' || !('urls' in server)) throw new Error('Servidor inválido');
      const urls: unknown[] = Array.isArray(server.urls) ? server.urls : [server.urls];
      if (!urls.length || !urls.every(url => typeof url === 'string' && /^(stun|stuns|turn|turns):[^\s/?#]+(?:\?transport=(udp|tcp))?$/.test(url))) throw new Error('URL inválida');
      if (('username' in server && typeof server.username !== 'string') || ('credential' in server && typeof server.credential !== 'string')) throw new Error('Credenciais inválidas');
      return { urls: urls as string[], ...('username' in server ? { username: server.username as string } : {}),
        ...('credential' in server ? { credential: server.credential as string } : {}) };
    });
    return { iceServers, hasTurn: iceServers.some(server => (server.urls as string[]).some(url => /^turns?:/.test(url))), invalid: false };
  } catch { return { iceServers: DEFAULT_ICE, hasTurn: false, invalid: true }; }
}
