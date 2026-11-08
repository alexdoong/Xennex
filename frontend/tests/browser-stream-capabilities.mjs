import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage();
  const source = await readFile('src/features/stream/streamCapabilities.ts', 'utf8');
  const script = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  await page.addScriptTag({ type: 'module', content: script + '\nwindow.preferCodecs = preferVideoCodecs; window.probeCodecsTest = probeCodecs;' });
  await page.waitForFunction(() => !!window.preferCodecs);
  const available = await page.evaluate(() => RTCRtpSender.getCapabilities('video').codecs.map(c => c.mimeType.toLowerCase()));
  const cases = [
    { name: 'advanced AV1 preference to VP8-only receiver', preferred: 'av1', allowed: 'vp8', expected: 'video/vp8' },
    { name: 'automatic browser negotiation', preferred: null, allowed: null, expected: null },
  ];
  if (available.includes('video/h264')) cases.push({ name: 'advanced AV1 preference to H264-only receiver', preferred: 'av1', allowed: 'h264', expected: 'video/h264' },
    { name: 'manual H264 preference with modern receiver', preferred: 'h264', allowed: null, expected: 'video/h264' });
  if (available.includes('video/av1')) cases.push({ name: 'AV1-capable sender and receiver', preferred: 'av1', allowed: 'av1', expected: 'video/av1' });
  for (const item of cases) {
    const result = await page.evaluate(async ({ preferred, allowed }) => {
      const sender = new RTCPeerConnection({ iceServers: [] }), receiver = new RTCPeerConnection({ iceServers: [] });
      const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 180;
      const context = canvas.getContext('2d'); let n = 0;
      const paint = setInterval(() => { context.fillStyle = '#211533'; context.fillRect(0, 0, 320, 180); context.fillStyle = '#ffccee'; context.fillRect(n++ * 9 % 280, 40, 40, 80); }, 35);
      const stream = canvas.captureStream(20);
      const video = document.createElement('video'); video.muted = true; document.body.append(video);
      receiver.ontrack = event => { video.srcObject = event.streams[0]; void video.play(); };
      const gathered = pc => pc.iceGatheringState === 'complete' ? Promise.resolve() : new Promise(resolve => pc.addEventListener('icegatheringstatechange', () => { if (pc.iceGatheringState === 'complete') resolve(); }));
      try {
        stream.getTracks().forEach(track => sender.addTrack(track, stream));
        const offer = await sender.createOffer();
        offer.sdp = window.preferCodecs(offer.sdp, preferred ? [preferred] : []);
        await sender.setLocalDescription(offer); await gathered(sender);
        await receiver.setRemoteDescription(sender.localDescription);
        if (allowed) for (const transceiver of receiver.getTransceivers()) {
          if (transceiver.receiver.track.kind === 'video') transceiver.setCodecPreferences(RTCRtpReceiver.getCapabilities('video').codecs.filter(c => c.mimeType.toLowerCase() === `video/${allowed}`));
        }
        const answer = await receiver.createAnswer();
        answer.sdp = window.preferCodecs(answer.sdp, preferred ? [preferred] : []);
        await receiver.setLocalDescription(answer); await gathered(receiver);
        await sender.setRemoteDescription(receiver.localDescription);
        let received; const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
          const stats = await receiver.getStats();
          const video = [...stats.values()].find(s => s.type === 'inbound-rtp' && s.kind === 'video');
          if (video?.framesDecoded >= 8) { received = { codec: stats.get(video.codecId)?.mimeType.toLowerCase(), frames: video.framesDecoded }; break; }
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        if (!received) throw new Error('No decoded video after codec negotiation');
        return received;
      } finally { clearInterval(paint); stream.getTracks().forEach(t => t.stop()); video.remove(); sender.close(); receiver.close(); }
    }, item);
    if (item.expected) assert.equal(result.codec, item.expected, item.name);
    assert(result.frames >= 8); console.log('PASS', item.name, JSON.stringify(result));
  }
} finally { await browser.close(); }
