// Opt-in synthetic GPU -> H.264 -> native WebRTC -> browser test. No room/desktop capture.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { createServer } from 'node:http';
import { launchNativeTestBrowser } from './native-test-browser.mjs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const output = resolve('../bin/streaming-qa');
const executable = resolve('../bin/NativeEncoderTests/net8.0-windows10.0.19041.0/NativeEncoderTests.exe');
const provenance = JSON.parse((await readFile(resolve('../bin/NativeWebRtc/build-info.json'), 'utf8')).replace(/^\uFEFF/, ''));
assert.equal(provenance.schema, 'xennex-native-webrtc-build-v1');
assert.equal(provenance.tls.version, '3.6.7');
assert.equal(provenance.datachannel.version, '0.24.6');
assert.equal(createHash('sha256').update(await readFile(resolve('../bin/NativeWebRtc/bin/libdatachannel.dll'))).digest('hex').toUpperCase(), provenance.sha256);
const background = process.env.XENNEX_RTC_BACKGROUND === '1';
const profile = process.env.XENNEX_RTC_PROFILE === '1080p120' ? { width: 1920, height: 1080, fps: 120 } : { width: 1280, height: 720, fps: 30 };
const frameCount = background ? Math.min(240, profile.fps * 4) : 120;
const allowLevelStress = process.env.XENNEX_RTC_ALLOW_LEVEL_STRESS === '1';
const passiveAnswer = process.env.XENNEX_RTC_PASSIVE_ANSWER === '1';
const negotiateLevel = process.env.XENNEX_RTC_NEGOTIATE_LEVEL === '1';
const tamperFingerprint = process.env.XENNEX_RTC_TAMPER_FINGERPRINT === '1';
const dropInitialIdr = process.env.XENNEX_RTC_DROP_INITIAL_IDR === '1';
const useWgcFixture = process.env.XENNEX_RTC_WGC_FIXTURE === '1';
const useAmf = process.env.XENNEX_RTC_AMF === '1';
let amfProvenance = null;
if (useAmf) {
  amfProvenance = JSON.parse((await readFile(resolve('../bin/NativeAmf/build-info.json'), 'utf8')).replace(/^\uFEFF/, ''));
  assert.equal(amfProvenance.schema, 'xennex-amf-probe-build-v1');
  assert.equal(createHash('sha256').update(await readFile(resolve('../bin/NativeAmf/Xennex.AmfProbe.dll'))).digest('hex').toUpperCase(), amfProvenance.sha256);
}
const server = createServer((_, response) => { response.writeHead(200, { 'Content-Type': 'text/html' }); response.end('<video autoplay muted playsinline width="640" height="360"></video>'); });
await new Promise(done => server.listen(0, '127.0.0.1', done));
const host = await launchNativeTestBrowser(chromium, background, output);
const browser = host.browser;
let child, fixture, watchdog;
async function runProbe() {
try {
  const page = host.page;
  if (background) await page.setContent('<video autoplay muted playsinline width="640" height="360"></video>');
  else await page.goto(`http://127.0.0.1:${server.address().port}`);
  let cdp, windowId;
  if (background) {
    cdp = await page.context().newCDPSession(page);
    const window = await cdp.send('Browser.getWindowForTarget');
    windowId = window.windowId;
    await cdp.send('Browser.setWindowBounds', { windowId: window.windowId, bounds: { windowState: 'minimized' } });
    let activity;
    for (let attempt = 0; attempt < 30; attempt++) {
      activity = await page.evaluate(() => ({ visibility: document.visibilityState, focused: document.hasFocus() }));
      if (activity.visibility === 'hidden' && !activity.focused) break;
      await new Promise(done => setTimeout(done, 100));
    }
    assert(activity.visibility === 'hidden' && !activity.focused, `Owned browser did not actually hide: ${JSON.stringify(activity)}`);
  }
  await page.evaluate(() => {
    const video = document.querySelector('video');
    const peer = new RTCPeerConnection({ iceServers: [] });
    window.nativePeer = peer;
    window.observedFrames = 0;
    window.nativeActivity = [];
    const activity = () => {
      if (window.nativeActivity.length < 32) window.nativeActivity.push({ at: performance.now(), visibility: document.visibilityState, focused: document.hasFocus() });
    };
    activity(); document.addEventListener('visibilitychange', activity);
    window.addEventListener('focus', activity); window.addEventListener('blur', activity);
    peer.ontrack = event => { video.srcObject = new MediaStream([event.track]); void video.play(); };
    const frame = () => {
      window.observedFrames++;
      if (window.resumeAt && window.resumeFirstFrameDelayMs === undefined) window.resumeFirstFrameDelayMs = performance.now() - window.resumeAt;
      video.requestVideoFrameCallback(frame);
    };
    video.requestVideoFrameCallback(frame);
  });
  const sourceArguments = [];
  if (useWgcFixture) {
    assert.equal(profile.width, 1280); assert.equal(profile.height, 720);
    fixture = spawn(resolve('../bin/NativeEncoderFixtures/Xennex.OpenGlFixture64.exe'), ['--wgc-fixture'], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    fixture.stderr.resume();
    const lines = createInterface({ input: fixture.stdout });
    const identity = await Promise.race([
      new Promise((done, fail) => { lines.once('line', done); fixture.once('error', fail); fixture.once('exit', () => fail(new Error('Owned fixture exited before identity'))); }),
      new Promise((_, fail) => setTimeout(() => fail(new Error('Owned WGC fixture startup timed out')), 10000).unref()),
    ]);
    lines.close();
    const [pid, hwnd] = identity.split(' ').map(Number);
    assert.equal(pid, fixture.pid); assert(Number.isSafeInteger(hwnd) && hwnd > 0);
    sourceArguments.push('--wgc-fixture-pid', String(pid), '--wgc-fixture-hwnd', String(hwnd));
  }
  child = spawn(executable, ['--encode', '--native-rtc', '--bgra', '--color', '--candidate', '1',
    '--width', String(profile.width), '--height', String(profile.height), '--fps', String(profile.fps), '--frames', String(frameCount),
    ...(dropInitialIdr ? ['--drop-initial-idr'] : []), ...(useAmf ? ['--amf'] : []), ...sourceArguments], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  // Child diagnostics are synthetic, but never relay raw native logs/SDP into reports.
  let stderrSize = 0, stderrTail = '';
  child.stderr.on('data', data => { stderrSize += data.length; stderrTail = (stderrTail + data.toString()).slice(-8192); if (stderrSize > 1048576) child.kill(); });
  const exit = new Promise((done, fail) => { child.once('error', fail); child.once('exit', code => done(code)); });
  watchdog = setTimeout(() => child.kill(), 45000);
  let result, withinNegotiatedLevel = false, levelCapability = null, hiddenStage = null;
  for await (const line of createInterface({ input: child.stdout })) {
    if (line.length > 131072) throw new Error('Native probe exceeded bounded output');
    const message = JSON.parse(line);
    if (message.Type === 'result') { result = message; continue; }
    if (message.Type === 'streaming') {
      if (background) {
        assert(message.DurationMs >= 1000 && message.DurationMs <= 8000);
        await new Promise(done => setTimeout(done, Math.floor(message.DurationMs / 2)));
        hiddenStage = await page.evaluate(async () => {
          const incoming = [...(await window.nativePeer.getStats()).values()].find(item => item.type === 'inbound-rtp' && item.kind === 'video');
          return { visibility: document.visibilityState, focused: document.hasFocus(), received: incoming?.framesReceived ?? 0,
            decoded: incoming?.framesDecoded ?? 0, displayed: window.observedFrames };
        });
        assert.equal(hiddenStage.visibility, 'hidden'); assert.equal(hiddenStage.focused, false);
        assert(hiddenStage.received > 0, 'RTP continues arriving while the real document is hidden');
        await page.evaluate(() => { window.resumeAt = performance.now(); });
        await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } });
        await page.bringToFront();
      }
      continue;
    }
    assert.equal(message.Type, 'offer');
    const answer = await page.evaluate(async ({ sdp, allowLevelStress, passiveAnswer, negotiateLevel, profile }) => {
      const peer = window.nativePeer;
      await peer.setRemoteDescription({ type: 'offer', sdp });
      const answer = await peer.createAnswer();
      const sourceProfile = sdp.match(/profile-level-id=([0-9a-f]{6})/i)?.[1];
      const defaultProfile = answer.sdp.match(/profile-level-id=([0-9a-f]{6})/i)?.[1];
      let capability = null;
      if (negotiateLevel && sourceProfile && defaultProfile && parseInt(sourceProfile.slice(4), 16) > parseInt(defaultProfile.slice(4), 16)) {
        const requestedProfile = defaultProfile.slice(0, 4) + sourceProfile.slice(4);
        let timeout;
        try {
          capability = await Promise.race([navigator.mediaCapabilities.decodingInfo({ type: 'webrtc', video: {
            contentType: `video/H264;profile-level-id=${requestedProfile};packetization-mode=1`,
            width: profile.width, height: profile.height, framerate: profile.fps, bitrate: 6000000,
          } }), new Promise((_, fail) => { timeout = setTimeout(() => fail(new Error('Receiver capability query timed out')), 1500); })]);
        } finally { clearTimeout(timeout); }
        if (!capability.supported) throw new Error('Receiver capability query rejected the higher native H.264 level');
        answer.sdp = answer.sdp.replaceAll(`profile-level-id=${defaultProfile}`, `profile-level-id=${requestedProfile}`);
      }
      // Default answer exercises the browser client/native TLS server path.
      await peer.setLocalDescription(passiveAnswer ? { type: 'answer', sdp: answer.sdp.replaceAll('a=setup:active', 'a=setup:passive') } : answer);
      if (/^m=video 0 /m.test(peer.localDescription.sdp)) {
        const offeredProfile = sdp.match(/profile-level-id=([0-9a-f]{6})/i)?.[1] ?? 'unknown';
        const profiles = RTCRtpReceiver.getCapabilities('video').codecs.filter(codec => codec.mimeType.toLowerCase() === 'video/h264')
          .map(codec => codec.sdpFmtpLine?.match(/profile-level-id=([0-9a-f]{6})/i)?.[1] ?? 'unspecified');
        throw new Error(`Browser rejected synthetic H.264 media: offered=${offeredProfile}, supported=${profiles.join(',')}`);
      }
      const source = sdp.match(/profile-level-id=([0-9a-f]{6})/i)?.[1];
      const receiver = peer.localDescription.sdp.match(/profile-level-id=([0-9a-f]{6})/i)?.[1];
      if (!source || !receiver) throw new Error('Missing H.264 profile/level in bounded test negotiation');
      const withinLevel = parseInt(source.slice(4), 16) <= parseInt(receiver.slice(4), 16);
      if (!withinLevel && !allowLevelStress) throw new Error('Requested source exceeds receiver-advertised H.264 level; decoder stress requires explicit opt-in');
      if (peer.iceGatheringState !== 'complete') await new Promise((done, fail) => {
        const timeout = setTimeout(() => fail(new Error(`Browser ICE gathering timed out (${peer.iceGatheringState}/${peer.signalingState}/${peer.iceConnectionState})`)), 10000);
        peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') { clearTimeout(timeout); done(); } });
      });
      return { sdp: peer.localDescription.sdp, withinLevel, capability };
    }, { sdp: message.Sdp, allowLevelStress, passiveAnswer, negotiateLevel, profile });
    withinNegotiatedLevel = answer.withinLevel;
    levelCapability = answer.capability;
    if (tamperFingerprint) {
      assert(/a=fingerprint:sha-256 [0-9A-F]{2}/i.test(answer.sdp), 'Synthetic answer has a fingerprint to invalidate');
      answer.sdp = answer.sdp.replace(/(a=fingerprint:sha-256 )([0-9A-F]{2})/i, (_, prefix, octet) => prefix + (octet === '00' ? 'FF' : '00'));
    }
    child.stdin.write(JSON.stringify({ Type: 'answer', Sdp: answer.sdp }) + '\n');
  }
  const code = await exit;
  const failureType = stderrTail.match(/Unhandled exception\. ([\w.]+):/)?.[1] ?? 'unknown';
  const operation = stderrTail.match(/Native RTC operation failed \((-?\d+)\)/)?.[1] ?? 'unknown';
  const incomplete = stderrTail.match(/Incomplete synthetic encode: (\d+\/\d+ input, \d+\/\d+ output)/)?.[1] ?? 'unknown';
  const timeoutStage = stderrTail.match(/(Native ICE gathering|Native media track|Browser answer) (?:timed out|did not open)/)?.[1] ?? 'unknown';
  const browserState = await page.evaluate(async () => {
    const stats = [...(await window.nativePeer.getStats()).values()];
    return { ice: window.nativePeer.iceConnectionState, connection: window.nativePeer.connectionState, gather: window.nativePeer.iceGatheringState,
      decoded: stats.filter(item => item.type === 'inbound-rtp' && item.kind === 'video').reduce((total, item) => total + (item.framesDecoded || 0), 0),
      localCandidates: stats.filter(item => item.type === 'local-candidate').length,
      remoteCandidates: stats.filter(item => item.type === 'remote-candidate').length,
      pairs: stats.filter(item => item.type === 'candidate-pair').map(item => ({ state: item.state, requestsSent: item.requestsSent, responsesReceived: item.responsesReceived })) };
  });
  const nativeCandidates = stderrTail.match(/Synthetic native ICE candidates: (\d+)/)?.[1] ?? 'unknown';
  const nativeStates = [...stderrTail.matchAll(/Synthetic native (peer|ICE) state: (\d)/g)].map(match => `${match[1]}:${match[2]}`).join(',');
  const tlsDiagnostic = stderrTail.match(/Synthetic TLS diagnostic: ([A-Za-z0-9 /()'-]{1,200})/)?.[1] ?? 'unknown';
  if (tamperFingerprint) {
    assert.notEqual(code, 0, 'Wrong certificate fingerprint must reject the native session');
    assert(nativeStates.includes('peer:4'), 'Native DTLS peer failed closed');
    assert.match(tlsDiagnostic, /^X509 - /, 'Rejection is in X509 certificate verification');
    assert.equal(browserState.decoded, 0, 'No media is sent after fingerprint mismatch');
    assert.equal(result, undefined, 'Failed authentication never reports a successful encode/send');
    console.log('PASS: incorrect synthetic DTLS fingerprint rejected; no decoded media');
    return;
  }
  assert.equal(code, 0, `Native transport probe failed; exit=${code}, type=${failureType}, operation=${operation}, encode=${incomplete}, timeout=${timeoutStage}, tls=${tlsDiagnostic}, nativeCandidates=${nativeCandidates}, nativeStates=${nativeStates}, browser=${JSON.stringify(browserState)}, stderrBytes=${stderrSize}`);
  assert(result, 'Native encoder/transport returned a bounded result');
  if (background) {
    for (let attempt = 0; attempt < 20; attempt++) {
      if (await page.evaluate(() => document.visibilityState === 'visible' && window.resumeFirstFrameDelayMs !== undefined)) break;
      await new Promise(done => setTimeout(done, 100));
    }
  }
  const receiver = await page.evaluate(async () => {
    const stats = [...(await window.nativePeer.getStats()).values()];
    const incoming = stats.find(item => item.type === 'inbound-rtp' && item.kind === 'video');
    const codec = incoming && stats.find(item => item.id === incoming.codecId);
    const video = document.querySelector('video');
    const canvas = document.createElement('canvas'); canvas.width = 4; canvas.height = 4;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(video, 0, 0, 4, 4);
    const quadrants = [[0, 0], [3, 0], [0, 3], [3, 3]].map(([x, y]) => [...context.getImageData(x, y, 1, 1).data].slice(0, 3));
    return { connection: window.nativePeer.connectionState, width: video.videoWidth, height: video.videoHeight,
      received: incoming?.framesReceived ?? null, decoded: incoming?.framesDecoded ?? null,
      bytesReceived: incoming?.bytesReceived ?? null, packetsReceived: incoming?.packetsReceived ?? null,
      displayed: window.observedFrames, codec: codec?.mimeType ?? null,
      negotiatedProfile: codec?.sdpFmtpLine?.match(/profile-level-id=([0-9a-f]{6})/i)?.[1] ?? null,
      quadrants,
      resumeFirstFrameDelayMs: window.resumeFirstFrameDelayMs ?? null,
      resumeAt: window.resumeAt ?? null, activity: window.nativeActivity,
      visibility: document.visibilityState, focused: document.hasFocus() };
  });
  assert.equal(receiver.codec?.toLowerCase(), 'video/h264');
  assert.equal(receiver.width, profile.width); assert.equal(receiver.height, profile.height);
  assert(receiver.decoded > 0, 'Browser independently decoded native H.264 RTP');
  const colors = [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]];
  const matches = expected => receiver.quadrants.every((pixel, quadrant) => pixel.every((value, channel) => Math.abs(value - expected[quadrant][channel]) < 35));
  assert(matches(colors) || matches([...colors].reverse()), 'Browser reproduces all four synthetic RGB quadrants');
  if (!background) assert(receiver.displayed > 0, 'Foreground browser displayed native H.264 RTP');
  if (background) {
    assert(hiddenStage, 'Hidden phase was measured during actual encoding');
    const restored = await cdp.send('Browser.getWindowBounds', { windowId });
    assert.equal(restored.bounds.windowState, 'normal', 'Owned window was restored');
    assert(receiver.activity.some(item => item.visibility === 'visible' && item.at >= receiver.resumeAt), 'Real document became visible after restoration; later refocus by the user is allowed');
    assert(receiver.resumeFirstFrameDelayMs !== null && receiver.resumeFirstFrameDelayMs < 2000, 'Video display resumes after restoring the owned test tab');
  }
  assert.equal(result.Sent, frameCount - (dropInitialIdr ? 1 : 0)); assert.equal(result.Encoder.Validation.Frames, frameCount);
  if (dropInitialIdr) {
    assert.equal(result.SkippedInitialIdr, 1);
    assert(result.PliReceived > 0 && result.Encoder.ForcedKeyframes > 0 && result.IdrObserved > 1, 'Receiver PLI reached the encoder and produced a fresh IDR');
  } else {
    assert(receiver.received >= result.Sent * .95 && (background || receiver.decoded >= result.Sent * .95),
      `Healthy transport receives at least95%; visible control also decodes at least95%: ${JSON.stringify({ sent: result.Sent, received: receiver.received, decoded: receiver.decoded, nalBytes: result.NalPayloadBytes })}`);
    assert(result.Encoder.ActualInputFps >= profile.fps * .95, 'Synthetic source meets at least95% of requested cadence');
  }
  await mkdir(output, { recursive: true });
  const variant = (useAmf ? '-amf' : '') + (useWgcFixture ? '-wgc-fixture' : '') + (dropInitialIdr ? '-pli-recovery' : !withinNegotiatedLevel ? '-level-stress' : negotiateLevel ? '-capability' : passiveAnswer ? '-passive' : '');
  await writeFile(resolve(output, `native-encoder-webrtc-${profile.width}-${profile.fps}${background ? '-hidden-resume' : ''}${variant}.json`), JSON.stringify({
    schema: result.Schema, sent: result.Sent, profile: result.Profile, withinNegotiatedLevel, diagnosticLevelStress: !withinNegotiatedLevel, passiveAnswer,
    hiddenStage, levelCapability, provenance, amfProvenance, source: useWgcFixture ? 'wgc-owned-fixture' : 'synthetic-textures', encoder: result.Encoder, receiver,
    pliReceived: result.PliReceived, idrObserved: result.IdrObserved, skippedInitialIdr: result.SkippedInitialIdr,
    nalPayloadBytes: result.NalPayloadBytes,
  }, null, 2));
  console.log(withinNegotiatedLevel ? 'PASS: synthetic native GPU/H.264/DTLS-SRTP/browser interoperability' : 'PASS: opt-in decoder stress above advertised level; NOT negotiated production capability', JSON.stringify(receiver));
} finally {
  clearTimeout(watchdog);
  if (child && child.exitCode === null) child.kill();
  if (fixture && fixture.exitCode === null) fixture.kill();
  await host.close();
  server.close();
}
}
await runProbe();
