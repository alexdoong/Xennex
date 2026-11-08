// Isolated WebView2 + own OpenGL fixture only. Never targets a running game.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
let browser, page, fixture;
try {
  for (let n = 0; n < 40 && !browser; n++) {
    try { browser = await chromium.connectOverCDP('http://127.0.0.1:9236'); }
    catch { await new Promise(resolve => setTimeout(resolve, 500)); }
  }
  assert(browser, 'Isolated WebView2 started');
  for (let n = 0; n < 40 && !page; n++) {
    page = browser.contexts()[0].pages().find(p => p.url().includes('appassets'));
    if (!page) await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert(page); await page.waitForFunction(() => !!window.chrome?.webview?.hostObjects?.api);
  let script = '';
  for (const name of ['quality', 'captureSocket', 'captureStartup', 'captureMetrics', 'frameDecoder', 'latestFrame', 'captureVideoOutput', 'captureFrameWorkerOutput', 'captureFramePipeline', 'browserCaptureSupport', 'capture']) {
    const source = (await readFile(new URL(`../src/features/stream/${name}.ts`, import.meta.url), 'utf8')).replace(/^import .*;\r?\n/gm, '');
    script += ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText + '\n';
  }
  await page.addScriptTag({ type: 'module', content: script + '\nwindow.gameCaptureTest = startCapture; window.gameQualityTest = tuneConnection;' });
  await page.waitForFunction(() => !!window.gameCaptureTest);
  assert(process.env.XENNEX_GAME_FIXTURE, 'Explicit own fixture path required');
  fixture = spawn(process.env.XENNEX_GAME_FIXTURE, [], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const lines = createInterface({ input: fixture.stdout });
  const identity = await Promise.race([
    new Promise((resolve, reject) => { lines.once('line', resolve); fixture.once('error', reject); }),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Own GL fixture startup timeout')), 10000).unref()),
  ]);
  const [pid, hwnd] = identity.split(' ').map(Number);
  assert.equal(pid, fixture.pid); assert(hwnd > 0);
  for (const fps of [30, 60, 120]) {
    const result = await page.evaluate(async ({ pid, hwnd, fps }) => {
      const quality = { resolution: '720p', fps, preference: 'motion', uploadMbps: 12, delivery: 'preserve' };
      const capture = await window.gameCaptureTest({ source: 'game', process: { Hwnd: hwnd, Pid: pid }, audio: 'none', quality }, new AbortController().signal, () => {});
      const sender = new RTCPeerConnection({ iceServers: [] }), receiver = new RTCPeerConnection({ iceServers: [] });
      const video = document.createElement('video'); video.muted = true;
      Object.assign(video.style, { position: 'fixed', right: '12px', bottom: '12px', width: '240px', height: '180px', zIndex: '2147483647' }); document.body.append(video);
      const a = [], b = [];
      sender.onicecandidate = ({ candidate }) => { if (candidate) { if (receiver.remoteDescription) void receiver.addIceCandidate(candidate); else a.push(candidate); } };
      receiver.onicecandidate = ({ candidate }) => { if (candidate) { if (sender.remoteDescription) void sender.addIceCandidate(candidate); else b.push(candidate); } };
      receiver.ontrack = ({ streams }) => { video.srcObject = streams[0]; void video.play(); };
      try {
        capture.stream.getTracks().forEach(track => sender.addTrack(track, capture.stream));
        await sender.setLocalDescription(await sender.createOffer()); await receiver.setRemoteDescription(sender.localDescription);
        for (const candidate of a) await receiver.addIceCandidate(candidate);
        await receiver.setLocalDescription(await receiver.createAnswer()); await sender.setRemoteDescription(receiver.localDescription);
        for (const candidate of b) await sender.addIceCandidate(candidate);
        const until = performance.now() + 10000;
        while ((!video.videoWidth || video.readyState < 2) && performance.now() < until) await new Promise(resolve => setTimeout(resolve, 50));
        if (!video.videoWidth) throw new Error('No received game video');
        await window.gameQualityTest(sender, quality, 1);
        await new Promise(resolve => setTimeout(resolve, 1000));
        const incoming = async () => [...(await receiver.getStats()).values()].find(v => v.type === 'inbound-rtp' && v.kind === 'video');
        const before = await incoming(), start = performance.now();
        await new Promise(resolve => setTimeout(resolve, 2500));
        const after = await incoming();
        const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        const context = canvas.getContext('2d'); context.drawImage(video, 0, 0);
        const top = [...context.getImageData(10, 10, 1, 1).data], bottom = [...context.getImageData(10, canvas.height - 10, 1, 1).data];
        return { target: fps, receivedFps: ((after.framesDecoded || 0) - (before.framesDecoded || 0)) * 1000 / (performance.now() - start),
          width: video.videoWidth, height: video.videoHeight, top, bottom, native: capture.nativeSession, pipeline: capture.pipeline,
          outgoing: [...(await sender.getStats()).values()].filter(v => v.type === 'outbound-rtp' && v.kind === 'video').map(v => ({ limitation: v.qualityLimitationReason, framesEncoded: v.framesEncoded, encoder: v.encoderImplementation })) };
      } finally { sender.close(); receiver.close(); video.srcObject = null; video.remove(); await capture.stop(); }
    }, { pid, hwnd, fps });
    assert(result.receivedFps > fps * .5 && result.width > 100 && result.native, 'Game image reaches real WebRTC receiver without slideshow');
    assert.equal(result.width, result.pipeline.worker.outputWidth, 'Preserve selected capture resolution at receiver');
    assert.equal(result.height, result.pipeline.worker.outputHeight);
    assert(result.top[2] > 160 && result.top[0] < 100 && result.bottom[0] > 160 && result.bottom[2] < 100, 'Received image preserves orientation and channels');
    delete result.top; delete result.bottom;
    console.log('MEASURE game IPC/JPEG/WebView2/WebRTC', JSON.stringify(result));
  }
  console.log('PASS own OpenGL fixture -> native bridge -> authenticated socket -> decode/canvas -> local WebRTC, three start/stop cycles.');
} finally {
  fixture?.kill();
  await page?.evaluate(() => window.chrome.webview.hostObjects.api.Shutdown()).catch(() => {});
  await browser?.close();
}
