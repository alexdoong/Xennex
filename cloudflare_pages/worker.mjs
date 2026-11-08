// Optional TURN broker. Static hosting and P2P remain usable with TURN_ENABLED=false.
// Never log request authorization, provider tokens, credentials or candidate addresses.
const PATH = '/api/turn-credentials';
const encoder = new TextEncoder();
const json = (status, message, headers = {}) => Response.json(message, { status, headers: {
  'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'X-Content-Type-Options': 'nosniff', ...headers,
} });
async function matchesSecret(value, expected) {
  const hash = async input => new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(input)));
  const [a, b] = await Promise.all([hash(value), hash(expected)]);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
function validatedServers(value) {
  if (!Array.isArray(value) || !value.length || value.length > 8) return null;
  let turn = false;
  const servers = [];
  for (const server of value) {
    if (!server || typeof server !== 'object') return null;
    const urls = typeof server.urls === 'string' ? [server.urls] : server.urls;
    if (!Array.isArray(urls) || !urls.length || urls.length > 12 || !urls.every(url => typeof url === 'string' &&
        /^(stun|turn|turns):(stun|turn)\.cloudflare\.com:(3478|5349|443|80)(\?transport=(udp|tcp))?$/.test(url))) return null;
    const relay = urls.some(url => /^turns?:/.test(url));
    if (relay && (typeof server.username !== 'string' || !server.username || server.username.length > 4096 ||
        typeof server.credential !== 'string' || !server.credential || server.credential.length > 4096)) return null;
    turn ||= relay;
    servers.push({ urls, ...(relay ? { username: server.username, credential: server.credential } : {}) });
  }
  return turn ? servers : null;
}
export async function handleTurn(request, env, send = fetch) {
  const origin = request.headers.get('Origin');
  const allowed = new Set([new URL(request.url).origin, ...(env.TURN_ALLOWED_ORIGINS || '').split(',').map(value => value.trim()).filter(Boolean)]);
  if (origin && !allowed.has(origin)) return json(403, { error: 'origin_denied' });
  const cors = origin ? { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin' } : {};
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { ...cors,
    'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization', 'Cache-Control': 'no-store' } });
  if (request.method !== 'POST') return json(405, { error: 'method_not_allowed' }, { ...cors, Allow: 'POST, OPTIONS' });
  if (env.TURN_ENABLED !== 'true') return json(503, { error: 'turn_disabled' }, cors);
  if (typeof env.TURN_ACCESS_CODE !== 'string' || env.TURN_ACCESS_CODE.length < 24 || env.TURN_ACCESS_CODE.length > 256 ||
      !/^[a-zA-Z0-9_-]{8,128}$/.test(env.TURN_KEY_ID || '') || !env.TURN_KEY_API_TOKEN || !env.TURN_RATE_LIMITER?.limit) {
    return json(503, { error: 'turn_not_configured' }, cors);
  }
  try {
    const key = request.headers.get('CF-Connecting-IP') || 'unknown';
    if (!(await env.TURN_RATE_LIMITER.limit({ key })).success) return json(429, { error: 'rate_limited' }, { ...cors, 'Retry-After': '60' });
    const authorization = request.headers.get('Authorization') || '';
    if (authorization.length > 300 || !await matchesSecret(authorization, `Bearer ${env.TURN_ACCESS_CODE}`)) return json(401, { error: 'unauthorized' }, cors);
    // TTL is set by the administrator, never by the caller. It is not a billing cap.
    const configured = Number(env.TURN_TTL_SECONDS || 43200);
    if (!Number.isInteger(configured) || configured < 600 || configured > 43200) return json(503, { error: 'invalid_ttl' }, cors);
    const issuedAt = Date.now();
    const response = await send(`https://rtc.live.cloudflare.com/v1/turn/keys/${env.TURN_KEY_ID}/credentials/generate-ice-servers`, {
      method: 'POST', headers: { Authorization: `Bearer ${env.TURN_KEY_API_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ttl: configured }), redirect: 'error', signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) return json(502, { error: 'provider_unavailable' }, cors);
    const raw = await response.text();
    if (raw.length > 20000) return json(502, { error: 'provider_response_invalid' }, cors);
    const iceServers = validatedServers(JSON.parse(raw).iceServers);
    if (!iceServers) return json(502, { error: 'provider_response_invalid' }, cors);
    return json(200, { iceServers, expiresAt: issuedAt + configured * 1000 }, cors);
  } catch { return json(502, { error: 'turn_unavailable' }, cors); }
}
export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname === PATH) return handleTurn(request, env);
    return env.ASSETS.fetch(request);
  },
};
