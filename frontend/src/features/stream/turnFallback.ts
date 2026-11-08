import { parseIceConfig } from './iceConfig';

export interface TurnLease { iceServers: RTCIceServer[]; expiresAt: number }
export function parseTurnLease(value: unknown, now = Date.now()): TurnLease {
  if (!value || typeof value !== 'object' || !('iceServers' in value) || !('expiresAt' in value) ||
      typeof value.expiresAt !== 'number' || !Number.isFinite(value.expiresAt) ||
      value.expiresAt < now + 30000 || value.expiresAt > now + 86400000) throw new Error('A conexão alternativa retornou credenciais inválidas ou vencidas.');
  const parsed = parseIceConfig(JSON.stringify(value.iceServers));
  if (parsed.invalid || !parsed.hasTurn || parsed.iceServers.length > 8) throw new Error('O servidor não forneceu uma retransmissão válida.');
  for (const server of parsed.iceServers) {
    const urls = typeof server.urls === 'string' ? [server.urls] : server.urls;
    if (urls.length > 12 || urls.some(url => url.length > 512)) throw new Error('Lista de rotas da retransmissão maior que o permitido.');
    if (urls.some(url => /^turns?:/.test(url)) && (!server.username || !server.credential ||
        typeof server.credential !== 'string' || server.credential.length > 4096 || server.username.length > 4096)) {
      throw new Error('Credenciais da retransmissão ausentes ou inválidas.');
    }
  }
  return { iceServers: parsed.iceServers, expiresAt: value.expiresAt };
}
export function turnEndpoint(base: string, configured = ''): string {
  const url = new URL(configured || '/api/turn-credentials', base);
  const local = url.hostname === '127.0.0.1' || url.hostname === '[::1]';
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) || url.username || url.password || url.hash || url.search || url.hostname === 'appassets') {
    throw new Error('Configure um endereço HTTPS público para a conexão alternativa.');
  }
  return url.href;
}
export async function requestTurnLease(endpoint: string, accessCode: string, signal: AbortSignal, send: typeof fetch = fetch): Promise<TurnLease> {
  if (signal.aborted) throw new DOMException('Cancelado', 'AbortError');
  if (accessCode.trim().length < 24 || accessCode.length > 256) throw new Error('Informe o código de acesso fornecido pelo dono da sala para a conexão alternativa.');
  const response = await send(endpoint, { method: 'POST', headers: { Authorization: `Bearer ${accessCode.trim()}` },
    cache: 'no-store', credentials: 'omit', redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]) });
  if (!response.ok) {
    const errors: Record<number, string> = {
      401: 'Código de acesso à conexão alternativa inválido.',
      403: 'Esta origem não foi autorizada no servidor da conexão alternativa.',
      404: 'A conexão alternativa ainda não foi publicada neste endereço.',
      429: 'Muitas tentativas. Aguarde um minuto antes de tentar novamente.',
      503: 'A conexão alternativa está desligada ou ainda não foi configurada pelo dono da sala.',
    };
    throw new Error(errors[response.status] || 'O servidor da conexão alternativa não respondeu. A conexão normal continua disponível.');
  }
  const body = await response.text();
  if (body.length > 20000) throw new Error('Resposta de retransmissão maior que o permitido.');
  if (signal.aborted) throw new DOMException('Cancelado', 'AbortError');
  let value: unknown;
  try { value = JSON.parse(body); } catch { throw new Error('O servidor retornou uma resposta de retransmissão inválida.'); }
  return parseTurnLease(value);
}
