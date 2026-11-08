// Run through test_stream_native.ps1 -Background. Only our separate WGC fixture is captured.
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { createInterface } from 'node:readline';
import { promisify } from 'node:util';
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, sep } from 'node:path';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const bitmapControl = process.env.XENNEX_NATIVE_BITMAP === '1';
const pacedFixture = process.env.XENNEX_NATIVE_PACED_FIXTURE === '1';
const exec = promisify(execFile);
const appHandle = Number(process.env.XENNEX_TEST_HWND);
assert(Number.isSafeInteger(appHandle) && appHandle > 0, 'Only the isolated app handle supplied by the runner is accepted');
const appDirectory = resolve(process.env.XENNEX_TEST_DIRECTORY || '');
const allowedRoot = fileURLToPath(new URL('../../bin/', import.meta.url));
assert(appDirectory.toLowerCase().startsWith((resolve(allowedRoot) + sep + 'StreamNative-').toLowerCase()), 'Restore is restricted to the runner\'s isolated app copy');
// A raw ShowWindow does not restore WPF/WebView visibility after Hide(). Invoke
// the app's own single-instance activation/RestoreFromTray instead.
const restore = () => exec(resolve(appDirectory, 'Xennex.exe'), [], { windowsHide: true, timeout: 10000 });
let browser, fixture;
const receiverBrowser = await chromium.launch({ channel: 'msedge', headless: true,
  ignoreDefaultArgs: ['--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding'] });
const watchdog = setTimeout(() => { void browser?.close().catch(() => {}); void receiverBrowser.close().catch(() => {}); }, 90000);
try {
  for (let attempt = 0; attempt < 40 && !browser; attempt++) {
    try { browser = await chromium.connectOverCDP('http://127.0.0.1:9236', { noDefaults: true }); }
    catch { await new Promise(done => setTimeout(done, 250)); }
  }
  assert(browser, 'Isolated WebView2 did not start');
  let sender;
  for (let attempt = 0; attempt < 40 && !sender; attempt++) {
    sender = browser.contexts()[0].pages().find(page => page.url().includes('appassets'));
    if (!sender) await new Promise(done => setTimeout(done, 250));
  }
  assert(sender, 'Isolated application page missing');
  await sender.waitForFunction(() => !!window.chrome?.webview?.hostObjects?.api, null, { polling: 100, timeout: 15000 });
  let script = '';
  for (const name of ['quality', 'captureSocket', 'captureStartup', 'captureMetrics', 'frameDecoder', 'latestFrame', 'captureVideoOutput', 'captureFrameWorkerOutput', 'captureFramePipeline', 'browserCaptureSupport', 'capture']) {
    let source = (await readFile(new URL(`../src/features/stream/${name}.ts`, import.meta.url), 'utf8')).replace(/^import .*;\r?\n/gm, '');
    if (bitmapControl && name === 'frameDecoder') source = source.replace("typeof globalThis.ImageDecoder === 'function' ? globalThis.ImageDecoder : undefined", 'undefined');
    script += ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText + '\n';
  }
  await sender.addScriptTag({ type: 'module', content: script + '\nwindow.backgroundStartCapture = startCapture; window.backgroundTuneConnection = tuneConnection;' });
  await sender.waitForFunction(() => !!window.backgroundStartCapture, null, { polling: 100 });
  const receiver = await receiverBrowser.newPage();
  await receiver.setContent('<video autoplay muted playsinline width="640" height="360"></video>');
  const results = [];
  for (const mode of ['canvas', 'auto']) {
    fixture = spawn(fileURLToPath(new URL('../../bin/NativeEncoderFixtures/Xennex.OpenGlFixture64.exe', import.meta.url)), [pacedFixture ? '--wgc-paced-fixture' : '--wgc-fixture'],
      { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    fixture.stderr.resume();
    const lines = createInterface({ input: fixture.stdout });
    const identity = await Promise.race([
      new Promise((done, fail) => { lines.once('line', done); fixture.once('error', fail); fixture.once('exit', () => fail(new Error('Owned fixture exited'))); }),
      new Promise((_, fail) => setTimeout(() => fail(new Error('Fixture identity deadline')), 10000).unref()),
    ]);
    lines.close();
    const [pid, hwnd] = identity.split(' ').map(Number);
    assert.equal(pid, fixture.pid); assert(Number.isSafeInteger(hwnd) && hwnd > 0);
    try {
      await restore();
      await sender.waitForFunction(() => document.visibilityState === 'visible', null, { polling: 100, timeout: 10000 });
      const source = await sender.evaluate(async ({ pid, hwnd, mode }) => {
        window.captureEnded = 0;
        window.backgroundCapture = await window.backgroundStartCapture({ source: 'window', process: { Hwnd: hwnd, Pid: pid }, audio: 'none', frameOutput: mode,
          quality: { resolution: '720p', fps: 30, preference: 'motion', uploadMbps: 12, delivery: 'preserve' } }, new AbortController().signal, () => window.captureEnded++);
        window.backgroundPeer = new RTCPeerConnection({ iceServers: [] });
        window.backgroundCapture.stream.getTracks().forEach(track => window.backgroundPeer.addTrack(track, window.backgroundCapture.stream));
        const peer = window.backgroundPeer; await peer.setLocalDescription(await peer.createOffer());
        if (peer.iceGatheringState !== 'complete') await new Promise((done, fail) => {
          const timeout = setTimeout(() => fail(new Error('Source ICE deadline')), 10000);
          peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') { clearTimeout(timeout); done(); } });
        });
        return peer.localDescription.toJSON();
      }, { pid, hwnd, mode });
      const answer = await receiver.evaluate(async source => {
        const peer = window.backgroundPeer = new RTCPeerConnection({ iceServers: [] });
        peer.ontrack = event => { document.querySelector('video').srcObject = new MediaStream([event.track]); };
        await peer.setRemoteDescription(source); await peer.setLocalDescription(await peer.createAnswer());
        if (peer.iceGatheringState !== 'complete') await new Promise((done, fail) => {
          const timeout = setTimeout(() => fail(new Error('Receiver ICE deadline')), 10000);
          peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') { clearTimeout(timeout); done(); } });
        });
        return peer.localDescription.toJSON();
      }, source);
      await sender.evaluate(async answer => {
        await window.backgroundPeer.setRemoteDescription(answer);
        await window.backgroundTuneConnection(window.backgroundPeer, { resolution: '720p', fps: 30, preference: 'motion', uploadMbps: 12, delivery: 'preserve' }, 1);
      }, answer);
      await receiver.waitForFunction(() => document.querySelector('video').videoWidth > 0, null, { polling: 100, timeout: 10000 });
      const snapshot = async () => ({
        source: await sender.evaluate(async () => {
          const stats = [...(await window.backgroundPeer.getStats()).values()].find(item => item.type === 'outbound-rtp' && item.kind === 'video');
          return { visibility: document.visibilityState, focused: document.hasFocus(), ended: window.captureEnded,
            encoded: stats?.framesEncoded ?? null, sent: stats?.framesSent ?? null, pipeline: window.backgroundCapture.pipeline ?? null };
        }),
        receiver: await receiver.evaluate(async () => {
          const stats = [...(await window.backgroundPeer.getStats()).values()].find(item => item.type === 'inbound-rtp' && item.kind === 'video');
          const video = document.querySelector('video');
          return { received: stats?.framesReceived ?? null, decoded: stats?.framesDecoded ?? null, width: video.videoWidth, height: video.videoHeight };
        }),
      });
      const measure = async () => {
        const begin = await snapshot(), start = Date.now();
        await new Promise(done => setTimeout(done, 5000));
        const end = await snapshot(), elapsedMs = Date.now() - start;
        const rate = (a, b) => typeof a === 'number' && typeof b === 'number' ? (b - a) * 1000 / elapsedMs : null;
        return { begin, end, elapsedMs, encodedFps: rate(begin.source.encoded, end.source.encoded), receivedFps: rate(begin.receiver.received, end.receiver.received), decodedFps: rate(begin.receiver.decoded, end.receiver.decoded) };
      };
      const visible = await measure();
      await sender.evaluate(() => window.chrome.webview.hostObjects.api.MinimizeToTray());
      await sender.waitForFunction(() => document.visibilityState === 'hidden' && !document.hasFocus(), null, { polling: 100, timeout: 10000 });
      const hidden = await measure();
      assert.equal(hidden.begin.source.visibility, 'hidden'); assert.equal(hidden.end.source.visibility, 'hidden');
      assert.equal(hidden.end.source.ended, 0);
      await restore();
      await sender.waitForFunction(() => document.visibilityState === 'visible', null, { polling: 100, timeout: 10000 });
      const resumed = await measure();
      const result = { mode, visible, hidden, resumed };
      results.push(result); console.log('MEASURE: actual WebView2/WGC JPEG pipeline', JSON.stringify(result));
      assert(hidden.receivedFps > 0 && resumed.receivedFps > 0, 'Capture must continue while hidden and after restoration');
      if (mode === 'auto') {
        assert.equal(hidden.end.source.pipeline?.output, 'generator');
        assert(hidden.receivedFps >= visible.receivedFps * .8, 'Hidden delivery must retain at least80% of this run\'s visible rate');
      }
    } finally {
      await restore().catch(() => {});
      await sender.evaluate(async () => { window.backgroundPeer?.close(); await window.backgroundCapture?.stop(); }).catch(() => {});
      await receiver.evaluate(() => window.backgroundPeer?.close()).catch(() => {});
      if (fixture?.exitCode === null) fixture.kill(); fixture = undefined;
    }
  }
  const folder = new URL('../../bin/streaming-qa/', import.meta.url);
  await mkdir(folder, { recursive: true });
  await writeFile(new URL(`capture-background-native${bitmapControl ? '-bitmap' : ''}${pacedFixture ? '-paced' : ''}.json`, folder), JSON.stringify({ schema: 'xennex-native-jpeg-background-v1', bitmapControl, pacedFixture, results }, null, 2));
  console.log('PASS: native WGC source/receiver measured with WebView2 genuinely hidden; this does not prove high-FPS targets or internet delivery');
} finally {
  clearTimeout(watchdog);
  if (fixture?.exitCode === null) fixture.kill();
  await receiverBrowser.close(); if (browser) await browser.close();
}
