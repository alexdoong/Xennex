import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage();
  const source = await readFile('src/features/stream/quality.ts', 'utf8');
  const script = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  await page.addScriptTag({ type: 'module', content: script + '\nwindow.testTune = tuneConnection;' });
  await page.waitForFunction(() => !!window.testTune);
  const result = await page.evaluate(async () => {
    const source = new RTCPeerConnection(), receiver = new RTCPeerConnection();
    const canvas = document.createElement('canvas'); canvas.width = 1920; canvas.height = 1080;
    const context = canvas.getContext('2d'); let frame = 0;
    const timer = setInterval(() => {
      context.fillStyle = '#24134c'; context.fillRect(0, 0, 1920, 1080);
      context.fillStyle = '#cdabff'; context.fillRect(++frame * 9 % 1700, 200, 220, 400);
    }, 16);
    const media = canvas.captureStream(60);
    const player = document.createElement('video'); player.muted = true; player.autoplay = true; document.body.append(player);
    receiver.ontrack = event => { player.srcObject = event.streams[0]; void player.play(); };
    // Exchange gathered SDP locally: no public signaling server or external video upload.
    const gathered = pc => pc.iceGatheringState === 'complete' ? Promise.resolve() : new Promise(resolve =>
      pc.addEventListener('icegatheringstatechange', () => { if (pc.iceGatheringState === 'complete') resolve(); }));
    try {
      media.getTracks().forEach(track => source.addTrack(track, media));
      await source.setLocalDescription(await source.createOffer()); await gathered(source);
      await receiver.setRemoteDescription(source.localDescription);
      await receiver.setLocalDescription(await receiver.createAnswer()); await gathered(receiver);
      await source.setRemoteDescription(receiver.localDescription);
      const deadline = Date.now() + 20000;
      while (source.connectionState !== 'connected') {
        if (Date.now() > deadline) throw new Error('Local WebRTC did not connect');
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      await window.testTune(source, { resolution: '1080p', fps: 60, preference: 'motion', uploadMbps: 30, delivery: 'preserve' }, 1);
      await new Promise(resolve => setTimeout(resolve, 6500));
      const out = [...(await source.getStats()).values()].find(r => r.type === 'outbound-rtp' && r.kind === 'video');
      const incoming = [...(await receiver.getStats()).values()].find(r => r.type === 'inbound-rtp' && r.kind === 'video');
      return { sent: { width: out?.frameWidth, height: out?.frameHeight, fps: out?.framesPerSecond, limitation: out?.qualityLimitationReason },
        received: { width: incoming?.frameWidth, height: incoming?.frameHeight, fps: incoming?.framesPerSecond },
        parameters: source.getSenders()[0].getParameters() };
    } finally { clearInterval(timer); media.getTracks().forEach(track => track.stop()); source.close(); receiver.close(); }
  });
  assert.equal(result.parameters.degradationPreference, 'maintain-resolution');
  assert.equal(result.parameters.encodings[0].maxFramerate, 60);
  assert.equal(result.sent.width, 1920); assert.equal(result.sent.height, 1080);
  assert.equal(result.received.width, 1920); assert.equal(result.received.height, 1080);
  assert(result.received.fps > 0);
  console.log('PASS: actual 1080p delivery with 60 FPS target:', JSON.stringify(result));
} finally { await browser.close(); }
