// Run only through scripts/tests/test_stream_native.ps1: captures that clean test app's own window.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const endpoint = 'http://127.0.0.1:9236';
let browser;
for (let attempt = 0; attempt < 40 && !browser; attempt++) {
  try { browser = await chromium.connectOverCDP(endpoint); }
  catch { await new Promise(resolve => setTimeout(resolve, 500)); }
}
if (!browser) throw new Error('Test WebView2 did not start');
let page;
try {
  for (let attempt = 0; attempt < 40 && !page; attempt++) {
    page = browser.contexts()[0].pages().find(page => page.url().includes('appassets'));
    if (!page) await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert(page, 'Clean test app page exists');
  await page.waitForFunction(() => !!window.chrome?.webview?.hostObjects?.api);
  let script = '';
  for (const name of ['quality', 'captureSocket', 'captureStartup', 'captureMetrics', 'frameDecoder', 'latestFrame', 'captureVideoOutput', 'captureFrameWorkerOutput', 'captureFramePipeline', 'browserCaptureSupport', 'capture']) {
    let source = (await readFile(new URL('../src/features/stream/' + name + '.ts', import.meta.url), 'utf8'))
      .replace(/^import .*;\r?\n/gm, '');
    if (process.env.XENNEX_NATIVE_AUTOMATIC === '1' && name === 'capture')
      source = source.replace('canvas.captureStream(0)', 'canvas.captureStream(captureFps(options.quality.fps))');
    script += ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText + '\n';
  }
  await page.addScriptTag({ type: 'module', content: script + '\nwindow.nativeCaptureTest = startCapture; window.nativeQualityTest = tuneConnection;' });
  await page.waitForFunction(() => !!window.nativeCaptureTest);
  const hwnd = Number(process.env.XENNEX_TEST_HWND);
  const pid = Number(process.env.XENNEX_TEST_PID);
  assert(hwnd > 0, 'Capture target must be the isolated test window');
  assert(Number.isInteger(pid) && pid > 0, 'Audio target must be the isolated test process');
  const monitorCount = await page.evaluate(async () => {
    const api = window.chrome.webview.hostObjects.api;
    const monitors = JSON.parse(await api.GetCaptureMonitors());
    if (!monitors.length || monitors.some(monitor => !monitor.Id || monitor.Width <= 0 || monitor.Height <= 0)) throw new Error('Invalid monitor metadata');
    const owner = crypto.randomUUID();
    if (!await api.TryBeginCapture(owner)) throw new Error('Test owner unavailable');
    try {
      if (!await api.BeginDesktopCapture(owner, 'missing-monitor-test', 30, '720p')) throw new Error('DXGI queue did not accept owner');
      for (let attempt = 0; attempt < 50; attempt++) {
        const state = JSON.parse(await api.GetCaptureState(owner));
        if (state.video === 'error') return monitors.length;
        if (state.video === 'ready') throw new Error('Unknown monitor must not fall back to another screen');
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      throw new Error('Missing monitor did not fail promptly');
    } finally {
      await api.EndCapture(owner);
      for (let attempt = 0; attempt < 80; attempt++) {
        if (JSON.parse(await api.GetCaptureState(owner)).phase === 'idle') break;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }
  });
  console.log('PASS: native bridge lists', monitorCount, 'monitors and rejects an unavailable monitor without capturing another');
  await page.evaluate(() => {
    document.getAnimations().forEach(animation => animation.cancel());
    const surface = document.createElement('canvas'); surface.id = 'native-test-source';
    surface.width = 1280; surface.height = 720;
    Object.assign(surface.style, { position: 'fixed', inset: '0', width: '100vw', height: '100vh', zIndex: '2147483647' });
    document.body.append(surface);
    const context = surface.getContext('2d'); context.fillStyle = '#18202a'; context.fillRect(0, 0, 1280, 720);
    window.nativeTestFrames = 0;
  });
  const cachedFrame = await page.evaluate(async hwnd => {
    const api = window.chrome.webview.hostObjects.api, owner = crypto.randomUUID();
    if (!await api.TryBeginCapture(owner)) throw new Error('Test capture ownership unavailable');
    try {
      if (!await api.BeginNativeCapture(owner, hwnd, 0, 30, '720p')) throw new Error('Test worker did not start');
      await new Promise(resolve => setTimeout(resolve, 1800));
      const token = encodeURIComponent(await api.GetCaptureToken());
      return await new Promise((resolve, reject) => {
        const socket = new WebSocket(`ws://127.0.0.1:59124/videostream/?token=${token}`);
        socket.binaryType = 'arraybuffer';
        const timeout = setTimeout(() => { socket.close(); reject(new Error('No cached frame for late static-source client')); }, 3000);
        socket.onmessage = event => { clearTimeout(timeout); socket.close(); resolve(event.data.byteLength); };
        socket.onerror = () => { clearTimeout(timeout); socket.close(); reject(new Error('Static-source socket failed')); };
      });
    } finally {
      await api.EndCapture(owner);
      for (let attempt = 0; attempt < 80; attempt++) {
        if (JSON.parse(await api.GetCaptureState(owner)).phase === 'idle') break;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }
  }, hwnd);
  assert(cachedFrame > 100, 'Late client receives actual JPEG bytes from a static window');
  console.log('PASS: static source supplies a frame to a client connecting after startup');
  for (let iteration = 0; iteration < 3; iteration++) {
    const result = await page.evaluate(async hwnd => {
      const begin = performance.now();
      const capture = await window.nativeCaptureTest({
        source: 'window', process: { Hwnd: hwnd, Pid: 0 }, audio: 'none',
        quality: { resolution: '720p', fps: 30, preference: 'detail', uploadMbps: 12, delivery: 'preserve' },
      }, new AbortController().signal, () => {});
      try {
        const denied = await new Promise(resolve => {
          const socket = new WebSocket('ws://127.0.0.1:59124/videostream/?token=wrong');
          const timeout = setTimeout(() => { socket.close(); resolve(false); }, 3000);
          socket.onopen = () => { clearTimeout(timeout); socket.close(); resolve(false); };
          socket.onerror = () => { clearTimeout(timeout); socket.close(); resolve(true); };
        });
        if (!denied) throw new Error('Video worker accepted an invalid token');
        const settings = capture.stream.getVideoTracks()[0].getSettings();
        return { elapsedMs: Math.round(performance.now() - begin), width: settings.width, height: settings.height };
      } finally { await capture.stop(); }
    }, hwnd);
    assert(result.width > 100 && result.height > 100);
    console.log('PASS: native worker starts on first attempt, cycle', iteration + 1, JSON.stringify(result));
  }
  const audioResult = await page.evaluate(async ({ hwnd, pid }) => {
    const capture = await window.nativeCaptureTest({ source: 'window', process: { Hwnd: hwnd, Pid: pid },
      audioProcess: { Hwnd: hwnd, Pid: pid }, audio: 'process',
      quality: { resolution: '720p', fps: 30, preference: 'detail', uploadMbps: 12, delivery: 'preserve' },
    }, new AbortController().signal, () => {});
    try {
      await new Promise(resolve => setTimeout(resolve, 1200));
      return { audioTracks: capture.stream.getAudioTracks().filter(track => track.readyState === 'live').length, warning: capture.warning };
    } finally { await capture.stop(); }
  }, { hwnd, pid });
  assert.equal(audioResult.audioTracks, 1, `Native audio startup failed: ${audioResult.warning}`);
  assert.equal(audioResult.warning, '');
  console.log('PASS: async native process audio starts and survives silence; only the isolated test app is targeted');
  await page.evaluate(() => {
    const surface = document.getElementById('native-test-source'), context = surface.getContext('2d');
    const paint = time => {
      window.nativeTestFrames++;
      context.fillStyle = '#18202a'; context.fillRect(0, 0, 1280, 720);
      context.fillStyle = '#b4e7fa'; context.fillRect((time / 3) % 1200, 100, 80, 520);
      context.font = '72px sans-serif'; context.fillText(String(window.nativeTestFrames), 40, 100);
      window.nativeTestAnimation = requestAnimationFrame(paint);
    };
    window.nativeTestAnimation = requestAnimationFrame(paint);
  });
  const pipeline = await page.evaluate(async hwnd => {
    // Smaller than the own test window: this must exercise WGC's GPU resize, not its bypass.
    const capture = await window.nativeCaptureTest({ source: 'window', process: { Hwnd: hwnd, Pid: 0 }, audio: 'none',
      quality: { resolution: '480p', fps: 30, preference: 'detail', uploadMbps: 12, delivery: 'preserve' },
    }, new AbortController().signal, () => {});
    try {
      const deadline = performance.now() + 7000;
      while (!capture.pipeline && performance.now() < deadline) await new Promise(resolve => setTimeout(resolve, 100));
      if (!capture.pipeline) throw new Error('Authenticated worker did not supply capture metrics');
      return capture.pipeline;
    } finally { await capture.stop(); }
  }, hwnd);
  assert.equal(pipeline.worker.scalePath, 'gpu'); assert(pipeline.worker.outputHeight <= 480);
  assert(pipeline.worker.mappedBytes < pipeline.worker.sourceBytes);
  assert(pipeline.decodeMs >= 0 && pipeline.drawMs >= 0);
  console.log('PASS: real WGC GPU resize, authenticated pipeline measurements and WebView decode/canvas timings', JSON.stringify(pipeline));
  const measurements = process.env.XENNEX_NATIVE_SMOKE_ONLY === '1' ? [{ fps: 60, hybrid: true, resolution: '1080p' }]
    : [{ fps: 30 }, { fps: 60 }, { fps: 120 }, { fps: 60, hybrid: true }, { fps: 60, hybrid: true, resolution: '1080p' }];
  for (const { fps, hybrid, resolution = '720p' } of measurements) {
    const workerStarts = async () => ((await readFile(join(process.env.XENNEX_TEST_DIRECTORY, 'logs', 'capture_worker.log'), 'utf8')).match(/Configuração:/g) || []).length;
    const startsBefore = hybrid ? await workerStarts() : 0;
    const measurement = await page.evaluate(async ({ hwnd, pid, fps, hybrid, resolution }) => {
      const quality = { resolution, fps, preference: 'motion', uploadMbps: 30, delivery: 'preserve' };
      const originalDisplay = navigator.mediaDevices.getDisplayMedia;
      if (hybrid) {
        const surface = document.getElementById('native-test-source');
        surface.width = resolution === '1080p' ? 1920 : 1280;
        surface.height = resolution === '1080p' ? 1080 : 720;
        navigator.mediaDevices.getDisplayMedia = async options => {
          if (options.audio !== false) throw new Error('Hybrid must not request duplicate browser audio');
          return surface.captureStream(fps);
        };
      }
      let capture;
      try {
        capture = await window.nativeCaptureTest({ source: hybrid ? 'browser' : 'window', process: { Hwnd: hwnd, Pid: pid },
          audio: hybrid ? 'process' : 'none', audioProcess: { Pid: pid }, quality }, new AbortController().signal, () => {});
      } finally { navigator.mediaDevices.getDisplayMedia = originalDisplay; }
      const sender = new RTCPeerConnection({ iceServers: [] }), receiver = new RTCPeerConnection({ iceServers: [] });
      const video = document.createElement('video'); video.muted = true;
      // Hidden receivers can throttle decoding, which is not the network delivery rate.
      Object.assign(video.style, { position: 'fixed', right: '12px', bottom: '12px', width: '240px', height: '180px', zIndex: '2147483647' });
      document.body.append(video);
      const pendingCandidates = [], pendingAnswers = [];
      sender.onicecandidate = ({ candidate }) => { if (candidate) { if (receiver.remoteDescription) void receiver.addIceCandidate(candidate); else pendingCandidates.push(candidate); } };
      receiver.onicecandidate = ({ candidate }) => { if (candidate) { if (sender.remoteDescription) void sender.addIceCandidate(candidate); else pendingAnswers.push(candidate); } };
      receiver.ontrack = ({ streams }) => { video.srcObject = streams[0]; void video.play(); };
      try {
        capture.stream.getTracks().forEach(track => sender.addTrack(track, capture.stream));
        await sender.setLocalDescription(await sender.createOffer()); await receiver.setRemoteDescription(sender.localDescription);
        for (const candidate of pendingCandidates) await receiver.addIceCandidate(candidate);
        await receiver.setLocalDescription(await receiver.createAnswer()); await sender.setRemoteDescription(receiver.localDescription);
        for (const candidate of pendingAnswers) await sender.addIceCandidate(candidate);
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('Local WebRTC did not connect')), 10000);
          const check = () => { if (sender.connectionState === 'connected') { clearTimeout(timeout); resolve(); } };
          sender.onconnectionstatechange = check; check();
        });
        await window.nativeQualityTest(sender, quality, 1);
        await new Promise(resolve => setTimeout(resolve, 1500));
        const incoming = async () => [...(await receiver.getStats()).values()].find(value => value.type === 'inbound-rtp' && value.kind === 'video');
        const outgoing = async () => [...(await sender.getStats()).values()].find(value => value.type === 'outbound-rtp' && value.kind === 'video');
        const activityBefore = { visibility: document.visibilityState, focused: document.hasFocus() };
        const before = await incoming(), sentBefore = await outgoing(), sourceFrames = window.nativeTestFrames, begin = performance.now();
        await new Promise(resolve => setTimeout(resolve, 4500));
        const after = await incoming(), sentAfter = await outgoing(), seconds = (performance.now() - begin) / 1000;
        return { mode: hybrid ? 'browser-video-process-audio' : 'native-jpeg', target: fps, width: after?.frameWidth, height: after?.frameHeight,
          audioTracks: capture.stream.getAudioTracks().filter(track => track.readyState === 'live').length,
          nativeSessionBusy: await window.chrome.webview.hostObjects.api.IsNativeWindowCapturing(),
          encodedFps: Math.round(((sentAfter?.framesEncoded || 0) - (sentBefore?.framesEncoded || 0)) / seconds * 10) / 10,
          arrivedFps: Math.round(((after?.framesReceived || 0) - (before?.framesReceived || 0)) / seconds * 10) / 10,
          receivedFps: Math.round(((after?.framesDecoded || 0) - (before?.framesDecoded || 0)) / seconds * 10) / 10,
          limitation: sentAfter?.qualityLimitationReason, encoder: sentAfter?.encoderImplementation,
          sourceFps: Math.round((window.nativeTestFrames - sourceFrames) / seconds * 10) / 10,
          activityBefore, activityAfter: { visibility: document.visibilityState, focused: document.hasFocus() },
          nativeProcessedFps: capture.pipeline?.worker?.processedFps ?? null };
      } finally { sender.close(); receiver.close(); video.srcObject = null; video.remove(); await capture.stop(); }
    }, { hwnd, pid, fps, hybrid, resolution });
    assert(measurement.receivedFps > 0 && measurement.width > 100, 'Native capture must reach a real WebRTC receiver');
    if (hybrid) { assert.equal(measurement.audioTracks, 1); assert.equal(measurement.nativeSessionBusy, true); assert.equal(await workerStarts(), startsBefore, 'Browser video must not start another native JPEG worker'); }
    if (hybrid && resolution === '1080p') { assert.equal(measurement.width, 1920); assert.equal(measurement.height, 1080); }
    console.log('MEASURE: capture/WebRTC', JSON.stringify(measurement));
  }
  await page.evaluate(() => { cancelAnimationFrame(window.nativeTestAnimation); document.getElementById('native-test-source').remove(); });
  await page.evaluate(() => { window.location.href = 'https://example.invalid/'; });
  await page.waitForTimeout(300);
  assert(page.url().startsWith('https://appassets/index.html'), 'External document must not replace the privileged interface');
  console.log('PASS: native video rejects invalid token and WebView2 blocks external navigation');
} finally {
  await page?.evaluate(() => window.chrome.webview.hostObjects.api.Shutdown()).catch(() => {});
  await browser.close();
}
