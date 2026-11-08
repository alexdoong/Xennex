import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const directory = await mkdtemp(resolve('node_modules/.stream-capabilities-'));
const saved = Object.fromEntries(['navigator', 'RTCRtpSender', 'RTCRtpReceiver', 'RTCPeerConnection'].map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
const set = (name, value) => Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
const codecCaps = names => ({ getCapabilities: () => ({ codecs: names.map(name => ({ mimeType: `video/${name}`, clockRate: 90000 })) }) });
const q = { resolution: '1080p', fps: 30, uploadMbps: 12, preference: 'motion' };
try {
  const source = await readFile('src/features/stream/streamCapabilities.ts', 'utf8');
  const file = resolve(directory, 'capabilities.mjs');
  await writeFile(file, ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  const { advertisedCodecs, probeCodecs, cachedCodecReport, codecOrder, codecMode, qualityHint, preferVideoCodecs, captureSupport } = await import(pathToFileURL(file));
  set('navigator', {}); set('RTCRtpSender', undefined); set('RTCRtpReceiver', undefined); set('RTCPeerConnection', undefined);
  assert.deepEqual(captureSupport(), { watch: false, screen: false, camera: false });
  assert.deepEqual(advertisedCodecs('encode'), []);
  assert.deepEqual(codecOrder('compatibility', 'decode'), ['h264', 'vp8', 'vp9', 'av1'], 'Compatibility can prefer only payloads present in real SDP even without detection APIs');
  assert.deepEqual((await probeCodecs(q, 'encode')).codecs, []);
  assert.equal(codecMode('NVENC'), 'auto');
  assert.equal(qualityHint({ resolution: '__proto__', fps: Infinity }).resolution, '1080p');
  assert.equal(qualityHint({ fps: 99999 }).fps, 120);
  set('RTCPeerConnection', class {});
  set('navigator', { mediaDevices: { getUserMedia() {} } });
  assert.deepEqual(captureSupport(), { watch: true, screen: false, camera: true }, 'Watching and camera remain available without screen capture');
  set('RTCRtpSender', codecCaps(['VP8'])); set('RTCRtpReceiver', codecCaps(['VP8']));
  const old = await probeCodecs({ ...q, fps: 31 }, 'encode');
  assert.deepEqual(old.codecs, [{ codec: 'vp8', advertised: true }]);
  assert.deepEqual(codecOrder('auto', 'encode', old), [], 'Unknown efficiency preserves browser order');
  assert.deepEqual(codecOrder('av1', 'encode', old), [], 'Unavailable preference falls back to normal negotiation');
  assert.deepEqual(codecOrder('compatibility', 'encode', old), ['vp8']);
  set('RTCRtpSender', codecCaps(['VP8', 'H264', 'AV1', 'VP9']));
  const requests = [];
  set('navigator', { mediaCapabilities: { async encodingInfo(configuration) {
    requests.push(configuration);
    const name = configuration.video.contentType;
    return { supported: name !== 'video/AV1', smooth: name !== 'video/AV1', powerEfficient: name === 'video/H264' };
  }, async decodingInfo() { return { supported: true, smooth: true, powerEfficient: true }; } } });
  const mixed = await probeCodecs({ ...q, fps: 60 }, 'encode');
  assert.equal(requests.length, 4); assert.equal(requests[0].type, 'webrtc'); assert.equal(requests[0].video.width, 1920); assert.equal(requests[0].video.framerate, 60);
  assert.equal(codecOrder('auto', 'encode', mixed)[0], 'h264', 'Prefer reported-efficient codec over software/unsupported alternatives');
  await probeCodecs({ ...q, fps: 60 }, 'encode'); assert.equal(requests.length, 4, 'Profile cache avoids repeated hardware queries');
  assert.equal(cachedCodecReport({ ...q, fps: 60 }, 'encode'), mixed);
  const receiver = await probeCodecs(q, 'decode');
  assert.deepEqual(receiver.codecs.map(v => v.codec), ['vp8'], 'Receiver has its own decoding capabilities');
  assert.deepEqual(codecOrder('av1', 'decode', receiver), []);
  set('navigator', { mediaCapabilities: { async encodingInfo() { throw new TypeError('WebRTC query not supported'); } } });
  const missing = await probeCodecs({ ...q, fps: 59 }, 'encode');
  assert(missing.codecs.every(c => c.supported === undefined));
  assert.deepEqual(codecOrder('auto', 'encode', missing), []);
  set('navigator', { mediaCapabilities: { encodingInfo: () => new Promise(() => {}) } });
  const start = performance.now(), timed = await probeCodecs({ ...q, fps: 58 }, 'encode');
  assert(performance.now() - start < 1500); assert(timed.codecs.every(c => c.supported === undefined), 'Slow probes stay unknown and bounded');
  set('navigator', Object.defineProperty({}, 'mediaCapabilities', { get() { throw new Error('Privacy policy'); } }));
  const denied = await probeCodecs({ ...q, fps: 57 }, 'encode');
  assert(denied.codecs.every(c => c.supported === undefined), 'Privacy restrictions never reject room negotiation');
  const lines = ['v=0', 'a=group:BUNDLE a v data', 'm=audio 9 UDP/TLS/RTP/SAVPF 111', 'a=rtpmap:111 opus/48000/2',
    'm=video 9 UDP/TLS/RTP/SAVPF 96 97 98 99 100 101 102 103 104', 'a=mid:v', 'a=ice-ufrag:unchanged',
    'a=rtpmap:96 VP8/90000', 'a=rtpmap:97 rtx/90000', 'a=fmtp:97 apt=96', 'a=rtpmap:98 H264/90000', 'a=rtpmap:99 rtx/90000', 'a=fmtp:99 apt=98',
    'a=fmtp:98 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f', 'a=rtpmap:100 AV1/90000',
    'a=rtpmap:101 H264/90000', 'a=fmtp:101 packetization-mode=1;profile-level-id=640c1f', 'a=rtpmap:102 red/90000',
    'a=rtpmap:103 ulpfec/90000', 'a=rtpmap:104 VP9/90000', 'm=application 9 UDP/DTLS/SCTP webrtc-datachannel', 'a=sctp-port:5000', ''];
  for (const separator of ['\r\n', '\n']) {
    const sdp = lines.join(separator), result = preferVideoCodecs(sdp, ['h264', 'vp8']);
    assert(result.includes('m=video 9 UDP/TLS/RTP/SAVPF 98 99 101 96 97 100 102 103 104'));
    assert.deepEqual(result.split(separator).filter(v => !v.startsWith('m=video')), lines.filter(v => !v.startsWith('m=video')), 'Only video payload order changes: profiles, RTX/FEC, audio, ICE and data remain');
    const originalPayloads = lines[4].split(' ').slice(3).sort(), sortedPayloads = result.split(separator)[4].split(' ').slice(3).sort();
    assert.deepEqual(sortedPayloads, originalPayloads, 'Never remove older viewer fallback codecs');
    assert.equal(preferVideoCodecs(sdp, []), sdp);
    assert.equal(preferVideoCodecs(sdp.replace('m=video 9', 'm=video 0'), ['h264']), sdp.replace('m=video 9', 'm=video 0'));
  }
  const legacy = 'v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=rtpmap:96 VP8/90000\r\n';
  assert.equal(preferVideoCodecs(legacy, ['av1']), legacy, 'AV1 preference cannot invent support on older receiver');
  assert.equal(preferVideoCodecs('x'.repeat(65537), ['h264']), 'x'.repeat(65537));
  console.log('PASS browser-first capabilities: missing/old APIs, independent receiver, cached/timed estimates, unsupported advanced preference and lossless SDP ordering.');
} finally {
  for (const [name, descriptor] of Object.entries(saved)) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name]; }
  await rm(directory, { recursive: true, force: true });
}
