// Opt-in: own Edge windows, synthetic JPEGs and local WebRTC only. No desktop capture.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash, randomBytes } from 'node:crypto';
import { createServer } from 'node:http';
import ts from 'typescript';
import { launchNativeTestBrowser } from './native-test-browser.mjs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const output = resolve('../bin/streaming-qa');
let script = '';
for (const name of ['frameDecoder', 'latestFrame', 'captureVideoOutput']) {
  const source = (await readFile(`src/features/stream/${name}.ts`, 'utf8')).replace(/^import .*;\r?\n/gm, '');
  script += ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText + '\n';
}
const receiverHost = await launchNativeTestBrowser(chromium, false, output);
const results = [];
try {
  const receiver = receiverHost.page;
  await receiver.setContent('<video autoplay muted playsinline width="640" height="360"></video>');
  const jpegs = (await receiver.evaluate(() => [false, true].map(reverse => {
    const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
    const context = canvas.getContext('2d');
    const colors = ['red', 'lime', 'blue', 'white'];
    (reverse ? colors.reverse() : colors).forEach((color, index) => {
      context.fillStyle = color; context.fillRect(index % 2 * 320, Math.floor(index / 2) * 180, 320, 180);
    });
    return canvas.toDataURL('image/jpeg', .8).split(',')[1];
  }))).map(value => Buffer.from(value, 'base64'));
  for (const mode of ['canvas', 'auto']) {
    const senderHost = await launchNativeTestBrowser(chromium, true, output);
    const sourceServer = createServer((_, response) => { response.writeHead(404); response.end(); });
    let productionTimer;
    let supplied = 0;
    let sourceSocket;
    try {
      const sender = senderHost.page;
      await sender.setContent('<p>Teste sintético de captura em segundo plano</p>');
      const cdp = await sender.context().newCDPSession(sender);
      const { windowId } = await cdp.send('Browser.getWindowForTarget');
      await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } });
      await sender.bringToFront();
      await sender.addScriptTag({ type: 'module', content: script + '\nwindow.CaptureVideoOutput = CaptureVideoOutput; window.CaptureFrameDecoder = CaptureFrameDecoder; window.LatestCaptureFrame = LatestCaptureFrame;' });
      await sender.waitForFunction(() => !!window.CaptureVideoOutput, null, { polling: 100, timeout: 10000 });
      const token = randomBytes(32).toString('hex');
      // Minimal one-way test fixture, not an application WebSocket implementation.
      // Exact opaque origin and random per-run token; listen only on loopback.
      sourceServer.on('upgrade', (request, socket) => {
        const key = request.headers['sec-websocket-key'];
        if (sourceSocket || request.method !== 'GET' || request.url !== `/${token}` || request.headers.origin !== 'null' ||
            request.headers['sec-websocket-version'] !== '13' || typeof key !== 'string' || Buffer.from(key, 'base64').length !== 16) { socket.destroy(); return; }
        sourceSocket = socket;
        const accept = createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
        socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
        // Node produces input independently of page timers, like the native worker.
        const epoch = performance.now(); let dueFrame = 0;
        productionTimer = setInterval(() => {
          const due = Math.floor((performance.now() - epoch) * 30 / 1000);
          if (due <= dueFrame) return;
          dueFrame = due; // No catch-up burst when the producer is delayed.
          if (socket.writableLength > 131072) return;
          const jpeg = jpegs[++supplied % 2];
          assert(jpeg.length > 125 && jpeg.length < 65536);
          const header = Buffer.alloc(4); header[0] = 0x82; header[1] = 126; header.writeUInt16BE(jpeg.length, 2);
          socket.write(Buffer.concat([header, jpeg]));
        }, 1);
        socket.on('data', () => socket.end(Buffer.from([0x88, 0]))); // Only close is expected from this test client.
        socket.on('close', () => clearInterval(productionTimer)); socket.on('error', () => {});
      });
      await new Promise(done => sourceServer.listen(0, '127.0.0.1', done));
      const socketUrl = `ws://127.0.0.1:${sourceServer.address().port}/${token}`;
      await sender.evaluate(({ mode, socketUrl }) => {
        window.sourceOutput = new window.CaptureVideoOutput(30, 'motion', mode);
        window.sourceDecoder = new window.CaptureFrameDecoder();
        window.sourceWritten = 0; window.sourceDropped = 0; window.sourceErrors = 0;
        window.senderPeer = new RTCPeerConnection({ iceServers: [] });
        window.sourceFrames = new window.LatestCaptureFrame(async bytes => {
          const frame = await window.sourceDecoder.decode(bytes);
          try { await window.sourceOutput.write(frame); window.sourceWritten++; }
          finally { frame.close(); }
          if (window.sourceWritten === 1) window.senderPeer.addTrack(window.sourceOutput.stream.getVideoTracks()[0]);
        }, () => window.sourceDropped++, error => { window.sourceErrors++; window.sourceErrorType = error?.name; });
        window.sourceSocket = new WebSocket(socketUrl); window.sourceSocket.binaryType = 'arraybuffer';
        window.sourceSocket.onmessage = event => { void window.sourceFrames.push(event.data); };
      }, { mode, socketUrl });
      try { await sender.waitForFunction(() => window.sourceWritten > 1, null, { polling: 100, timeout: 10000 }); }
      catch {
        const failure = await sender.evaluate(() => ({ socket: window.sourceSocket?.readyState, written: window.sourceWritten,
          errors: window.sourceErrors, errorType: window.sourceErrorType, path: window.sourceOutput.path, visibility: document.visibilityState }));
        throw new Error(`Synthetic source startup failed: ${JSON.stringify({ supplied, ...failure })}`);
      }
      await receiver.evaluate(() => {
        const peer = window.receiverPeer = new RTCPeerConnection({ iceServers: [] });
        peer.ontrack = event => { document.querySelector('video').srcObject = new MediaStream([event.track]); };
      });
      const offer = await sender.evaluate(async () => {
        const peer = window.senderPeer;
        await peer.setLocalDescription(await peer.createOffer());
        if (peer.iceGatheringState !== 'complete') await new Promise((done, fail) => {
          const timeout = setTimeout(() => fail(new Error('Synthetic source ICE deadline')), 10000);
          peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') { clearTimeout(timeout); done(); } });
        });
        return peer.localDescription.toJSON();
      });
      const answer = await receiver.evaluate(async offer => {
        const peer = window.receiverPeer;
        await peer.setRemoteDescription(offer); await peer.setLocalDescription(await peer.createAnswer());
        if (peer.iceGatheringState !== 'complete') await new Promise((done, fail) => {
          const timeout = setTimeout(() => fail(new Error('Synthetic receiver ICE deadline')), 10000);
          peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') { clearTimeout(timeout); done(); } });
        });
        return peer.localDescription.toJSON();
      }, offer);
      await sender.evaluate(answer => window.senderPeer.setRemoteDescription(answer), answer);
      await receiver.waitForFunction(() => document.querySelector('video').videoWidth > 0, null, { polling: 100, timeout: 10000 });
      await new Promise(done => setTimeout(done, 1000));
      await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'minimized' } });
      let activity;
      for (let attempt = 0; attempt < 30; attempt++) {
        activity = await sender.evaluate(() => ({ visibility: document.visibilityState, focused: document.hasFocus() }));
        if (activity.visibility === 'hidden' && !activity.focused) break;
        await new Promise(done => setTimeout(done, 100));
      }
      assert.deepEqual(activity, { visibility: 'hidden', focused: false }, 'Test must confirm real hidden state, never emulate it');
      const counters = async () => ({
        sender: await sender.evaluate(async () => {
          const stats = [...(await window.senderPeer.getStats()).values()].find(item => item.type === 'outbound-rtp' && item.kind === 'video');
          return { visibility: document.visibilityState, focused: document.hasFocus(), written: window.sourceWritten, dropped: window.sourceDropped, errors: window.sourceErrors,
            encoded: stats?.framesEncoded ?? null, sent: stats?.framesSent ?? null, path: window.sourceOutput.path };
        }),
        receiver: await receiver.evaluate(async () => {
          const stats = [...(await window.receiverPeer.getStats()).values()].find(item => item.type === 'inbound-rtp' && item.kind === 'video');
          return { received: stats?.framesReceived ?? null, decoded: stats?.framesDecoded ?? null };
        }),
      });
      const begin = await counters(), start = Date.now(), initialSupplied = supplied;
      await new Promise(done => setTimeout(done, 6000));
      const end = await counters(), elapsedMs = Date.now() - start;
      assert.equal(end.sender.visibility, 'hidden'); assert.equal(end.sender.focused, false);
      const rate = (at, after) => typeof at === 'number' && typeof after === 'number' ? (after - at) * 1000 / elapsedMs : null;
      const result = { mode, elapsedMs, supplied: supplied - initialSupplied, begin, end,
        inputFps: rate(begin.sender.written, end.sender.written), encodedFps: rate(begin.sender.encoded, end.sender.encoded),
        receivedFps: rate(begin.receiver.received, end.receiver.received), decodedFps: rate(begin.receiver.decoded, end.receiver.decoded) };
      console.log('Measured real hidden source', JSON.stringify(result));
      results.push(result);
      if (mode === 'auto') {
        assert.equal(end.sender.path, 'generator', 'This integration specifically validates the optional generator path');
        assert(result.inputFps >= 27 && result.encodedFps >= 27 && result.receivedFps >= 27 && result.decodedFps >= 27, 'Generated source maintains at least90% of30FPS while hidden');
        assert.equal(end.sender.errors, 0);
      }
      await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } });
      await sender.evaluate(() => { window.sourceSocket.close(); window.sourceFrames.stop(); window.sourceDecoder.stop(); window.sourceOutput.stop(); window.senderPeer.close(); });
      await receiver.evaluate(() => window.receiverPeer.close());
    } finally { clearInterval(productionTimer); sourceSocket?.destroy(); sourceServer.close(); await senderHost.close(); }
  }
  await mkdir(output, { recursive: true });
  await writeFile(resolve(output, 'capture-output-real-hidden.json'), JSON.stringify({ schema: 'xennex-capture-output-hidden-v1', results }, null, 2));
  console.log('PASS: generated JPEG source/WebRTC continues with a genuinely hidden publisher; canvas compatibility measured separately');
} finally { await receiverHost.close(); }
