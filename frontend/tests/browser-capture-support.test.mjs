import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const directory = await mkdtemp(resolve('node_modules/.browser-capture-'));
const names = ['navigator', 'isSecureContext', 'document', 'window', 'RTCPeerConnection'];
const saved = new Map(names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
const set = (name, value) => Object.defineProperty(globalThis, name, { configurable: true, value });
try {
  const source = await readFile('src/features/stream/browserCaptureSupport.ts', 'utf8');
  const file = resolve(directory, 'support.mjs');
  await writeFile(file, ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  const { browserCaptureStatus: status, screenCaptureFailure: failure, browserCaptureReport: report } = await import(pathToFileURL(file));
  set('navigator', { mediaDevices: { getUserMedia() {} }, userAgent: 'Android' });
  set('isSecureContext', true); set('document', undefined); set('window', undefined); set('RTCPeerConnection', class {});
  assert.equal(status().screen, 'missing-api'); assert.equal(status().camera, true); assert.equal(status().watch, true);
  set('navigator', { mediaDevices: { getDisplayMedia() {} }, userAgent: 'Android or future iPhone' });
  assert.equal(status().screen, 'available', 'A mobile UA must never block a working capture API');
  set('isSecureContext', false); assert.equal(status().screen, 'insecure');
  set('isSecureContext', true); set('document', { permissionsPolicy: { allowsFeature: () => false } });
  assert.equal(status().screen, 'policy-blocked');
  set('document', { featurePolicy: { allowsFeature() { throw new Error('unavailable'); } } });
  assert.equal(status().screen, 'available'); assert.equal(status().policy, null);
  assert.match(failure({ name: 'NotAllowedError' }), /cancelada/);
  assert.equal(failure({ name: 'AbortError' }), undefined);
  assert.doesNotMatch(report(), /Android|iPhone|room=|192\.168|userAgent/);
  console.log('PASS browser capture capabilities, permission errors and private diagnostic');
} finally {
  for (const [name, descriptor] of saved) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name]; }
  await rm(directory, { recursive: true, force: true });
}
