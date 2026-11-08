import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
import worker, { handleTurn } from '../../cloudflare_pages/worker.mjs';

const directory = await mkdtemp(resolve('node_modules/.turn-tests-'));
const relay = [{ urls: ['stun:stun.cloudflare.com:3478'] }, {
  urls: ['turn:turn.cloudflare.com:3478?transport=udp', 'turns:turn.cloudflare.com:443?transport=tcp'], username: 'fixture-user', credential: 'fixture-credential',
}];
try {
  for (const name of ['iceConfig', 'turnFallback']) {
    const code = (await readFile(`src/features/stream/${name}.ts`, 'utf8')).replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'");
    await writeFile(resolve(directory, `${name}.mjs`), ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  }
  const { parseTurnLease, requestTurnLease, turnEndpoint } = await import(pathToFileURL(resolve(directory, 'turnFallback.mjs')));
  const lease = { iceServers: relay, expiresAt: Date.now() + 600000 };
  assert.equal(parseTurnLease(lease).iceServers.length, 2);
  for (const invalid of [null, {}, { ...lease, expiresAt: 1 }, { ...lease, expiresAt: Infinity },
    { ...lease, iceServers: [{ urls: 'https://evil.test' }] }, { ...lease, iceServers: [{ urls: 'turn:relay.test' }] },
    { ...lease, iceServers: [{ urls: 'stun:stun.cloudflare.com:3478' }] }]) assert.throws(() => parseTurnLease(invalid));
  assert.equal(turnEndpoint('https://example.test/?room=XNX-TEST'), 'https://example.test/api/turn-credentials');
  assert.throws(() => turnEndpoint('https://appassets/'));
  for (const invalid of ['http://evil.test/', 'https://user:password@example.test/', 'https://example.test/?token=secret', 'https://example.test/#secret']) {
    assert.throws(() => turnEndpoint('https://example.test/', invalid));
  }
  let requests = 0;
  const send = async (_url, options) => {
    requests++;
    assert.equal(options.credentials, 'omit'); assert.equal(options.cache, 'no-store'); assert.equal(options.redirect, 'error');
    assert.equal(options.headers.Authorization, 'Bearer ' + 'a'.repeat(32));
    return Response.json(lease);
  };
  const cancelled = new AbortController(); cancelled.abort();
  await assert.rejects(requestTurnLease('https://example.test/api/turn-credentials', 'a'.repeat(32), cancelled.signal, send), { name: 'AbortError' });
  await assert.rejects(requestTurnLease('https://example.test/api/turn-credentials', '', new AbortController().signal, send), /código de acesso/);
  assert.equal(requests, 0);
  await requestTurnLease('https://example.test/api/turn-credentials', 'a'.repeat(32), new AbortController().signal, send);
  assert.equal(requests, 1);
  const lateController = new AbortController(); let releaseBody;
  const lateBody = new Promise(resolve => { releaseBody = resolve; });
  const lateRequest = requestTurnLease('https://example.test/api/turn-credentials', 'a'.repeat(32), lateController.signal,
    async () => ({ ok: true, text: () => lateBody }));
  lateController.abort(); releaseBody(JSON.stringify(lease));
  await assert.rejects(lateRequest, { name: 'AbortError' });
  for (const status of [401, 403, 404, 429, 503]) {
    await assert.rejects(requestTurnLease('https://example.test/api/turn-credentials', 'a'.repeat(32), new AbortController().signal,
      async () => new Response('PRIVATE PROVIDER ERROR', { status })), error => !error.message.includes('PRIVATE'));
  }
  await assert.rejects(requestTurnLease('https://example.test/api/turn-credentials', 'a'.repeat(32), new AbortController().signal,
    async () => new Response('PRIVATE-PROVIDER-RESPONSE')), error => !error.message.includes('PRIVATE'));
  console.log('PASS: TURN client validates expiry/configuration, cancellation, endpoint and sanitized errors before admission');

  let providerCalls = 0;
  const env = { TURN_ENABLED: 'true', TURN_ACCESS_CODE: 'private-access-'.repeat(3), TURN_KEY_ID: 'key-fixture-1234', TURN_KEY_API_TOKEN: 'PRIVATE-API-KEY',
    TURN_TTL_SECONDS: '600', TURN_ALLOWED_ORIGINS: 'https://appassets', TURN_RATE_LIMITER: { async limit() { return { success: true }; } } };
  const request = (headers = {}, method = 'POST') => new Request('https://example.test/api/turn-credentials', {
    method, headers: { Origin: 'https://example.test', Authorization: `Bearer ${env.TURN_ACCESS_CODE}`, ...headers },
  });
  const provider = async (url, options) => {
    providerCalls++; assert(url.startsWith('https://rtc.live.cloudflare.com/v1/turn/keys/key-fixture-1234/'));
    assert.deepEqual(JSON.parse(options.body), { ttl: 600 }); assert.equal(options.headers.Authorization, 'Bearer PRIVATE-API-KEY');
    return Response.json({ iceServers: relay });
  };
  assert.equal((await handleTurn(request(), { ...env, TURN_ENABLED: 'false' }, provider)).status, 503);
  assert.equal((await handleTurn(request({ Origin: 'https://evil.test' }), env, provider)).status, 403);
  assert.equal((await handleTurn(request(), { ...env, TURN_RATE_LIMITER: undefined }, provider)).status, 503);
  assert.equal((await handleTurn(request({}, 'GET'), env, provider)).status, 405);
  assert.equal((await handleTurn(request({ Authorization: 'Bearer wrong' }), env, provider)).status, 401);
  assert.equal((await handleTurn(request(), { ...env, TURN_RATE_LIMITER: { async limit() { return { success: false }; } } }, provider)).status, 429);
  assert.equal(providerCalls, 0, 'Disabled/unauthorized/rate-limited attempts never request billable credentials');
  const preflight = await handleTurn(request({ Origin: 'https://appassets' }, 'OPTIONS'), env, provider);
  assert.equal(preflight.status, 204); assert.equal(preflight.headers.get('Access-Control-Allow-Origin'), 'https://appassets');
  const response = await handleTurn(request(), env, provider);
  assert.equal(response.status, 200); assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.equal(response.headers.get('Access-Control-Allow-Origin'), 'https://example.test');
  const result = await response.json(); assert.deepEqual(result.iceServers, relay); assert(result.expiresAt > Date.now());
  assert(!JSON.stringify(result).includes('PRIVATE-API-KEY'));
  assert.equal(providerCalls, 1);
  const upstreamFailed = await handleTurn(request(), env, async () => new Response('PRIVATE-API-KEY', { status: 403 }));
  assert.equal(upstreamFailed.status, 502); assert(!(await upstreamFailed.text()).includes('PRIVATE'));
  const untrusted = await handleTurn(request(), env, async () => Response.json({ iceServers: [{ urls: 'turn:evil.test', username: 'x', credential: 'x' }] }));
  assert.equal(untrusted.status, 502);
  let assets = 0;
  const asset = await worker.fetch(new Request('https://example.test/'), { ASSETS: { async fetch() { assets++; return new Response('static-page'); } } });
  assert.equal(await asset.text(), 'static-page'); assert.equal(assets, 1);
  console.log('PASS: Worker defaults off, authenticates origin/access, enforces rate limit and TTL, protects API secrets and preserves static hosting');
} finally { await rm(directory, { recursive: true, force: true }); }
