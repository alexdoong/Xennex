import { QUALITY_PRESETS, captureFps, requestedFps, type Quality } from './quality';
export type NativeApi = Window['chrome']['webview']['hostObjects']['api'];
export interface AudioProcess { Pid: number; Hwnd: number; Name: string; Title: string; HasActiveAudio: boolean; PeakVolume: number }
export interface CaptureOptions { source: 'browser' | 'window' | 'monitor' | 'camera'; cameraId?: string; process?: AudioProcess; audio: 'none' | 'system' | 'process' | 'microphone'; quality: Quality }
export interface CaptureHandle { stream: MediaStream; source: string; warning: string; stop(): Promise<void> }
export const nativeApi = (): NativeApi | undefined => window.chrome?.webview?.hostObjects?.api;

function openSocket(url: string, signal: AbortSignal): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url); ws.binaryType = 'arraybuffer';
    const timer = setTimeout(() => { ws.close(); reject(new Error('A captura local não respondeu.')); }, 6000);
    const abort = () => { clearTimeout(timer); ws.close(); reject(new DOMException('Captura cancelada', 'AbortError')); };
    signal.addEventListener('abort', abort, { once: true });
    ws.onopen = () => { clearTimeout(timer); if (signal.aborted) abort(); else resolve(ws); };
    ws.onerror = () => { clearTimeout(timer); ws.close(); reject(new Error('Não foi possível conectar à captura local.')); };
    ws.addEventListener('close', () => signal.removeEventListener('abort', abort), { once: true });
  });
}

export async function startCapture(options: CaptureOptions, signal: AbortSignal, onEnded: () => void): Promise<CaptureHandle> {
  const api = nativeApi();
  const owner = crypto.randomUUID();
  const resources: (() => void | Promise<void>)[] = [];
  let stopped = false;
  let stream: MediaStream | undefined;
  let warning = '';
  const stop = async () => {
    if (stopped) return; stopped = true;
    signal.removeEventListener('abort', abort);
    stream?.getTracks().forEach(track => track.stop());
    for (const release of resources.reverse()) { try { await release(); } catch (error) { console.warn('[Capture] Limpeza:', error); } }
  };
  const abort = () => { stream?.getTracks().forEach(track => track.stop()); };
  const check = () => { if (signal.aborted || stopped) throw new DOMException('Captura cancelada', 'AbortError'); };
  signal.addEventListener('abort', abort, { once: true });
  try {
    check();
    if (options.source === 'camera') {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Câmera indisponível. Abra em HTTPS ou no aplicativo.');
      const preset = QUALITY_PRESETS[options.quality.resolution];
      stream = await navigator.mediaDevices.getUserMedia({
        video: { ...(options.cameraId ? { deviceId: { exact: options.cameraId } } : {}),
          ...(preset.width ? { width: { ideal: preset.width }, height: { ideal: preset.height } } : {}),
          ...(requestedFps(options.quality.fps) ? { frameRate: { ideal: captureFps(options.quality.fps), max: captureFps(options.quality.fps) } } : {}) },
        audio: options.audio === 'microphone' ? { echoCancellation: true, noiseSuppression: true } : false,
      });
      if (signal.aborted || stopped) { stream.getTracks().forEach(track => track.stop()); check(); }
      stream.getVideoTracks()[0].contentHint = options.quality.preference;
    } else if (options.source === 'browser') {
      if (!navigator.mediaDevices?.getDisplayMedia) throw new Error('Compartilhamento de tela indisponível neste navegador. Abra em HTTPS em um navegador compatível.');
      // Request during the click gesture, before any network/native await.
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: requestedFps(options.quality.fps) ? { frameRate: { ideal: captureFps(options.quality.fps), max: captureFps(options.quality.fps) } } : true,
        audio: options.audio !== 'none' ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false } : false,
      });
      if (signal.aborted || stopped) { stream.getTracks().forEach(track => track.stop()); check(); }
      const track = stream.getVideoTracks()[0];
      if (!track) throw new Error('Nenhuma tela foi selecionada.');
      const preset = QUALITY_PRESETS[options.quality.resolution];
      track.contentHint = options.quality.preference;
      if (preset.width) {
        try { await track.applyConstraints({ width: { max: preset.width }, height: { max: preset.height }, frameRate: { max: captureFps(options.quality.fps) } }); }
        catch { warning = 'O navegador manteve o formato disponível da fonte. Confira as medidas na prévia.'; }
      }
    } else {
      if (!api) throw new Error('Captura nativa disponível apenas no aplicativo.');
      if (options.source === 'window' && !options.process?.Hwnd) throw new Error('Selecione uma janela antes de compartilhar.');
      const acquired = await api.TryBeginCapture(owner);
      if (!acquired) throw new Error('Outra janela do Xennex já está compartilhando. Pare essa captura primeiro.');
      if (signal.aborted || stopped) { await api.EndCapture(owner); check(); }
      resources.push(() => api.EndCapture(owner));
      window.chrome.webview.postMessage(`capture-owner:${owner}`);
      const started = await api.StartNativeWindowCapture(options.source === 'window' ? options.process!.Hwnd : 0,
        options.process?.Pid || 0, captureFps(options.quality.fps), options.quality.resolution);
      check();
      if (!started) throw new Error('A captura nativa não iniciou. Tente a opção de seleção pelo navegador.');
      const ws = await openSocket('ws://127.0.0.1:59124/videostream/', signal);
      resources.push(() => ws.close()); check();
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d', { alpha: false });
      if (!context) throw new Error('Não foi possível criar a superfície de vídeo.');
      stream = await new Promise<MediaStream>((resolve, reject) => {
        let initialized = false; let decoding = false;
        const timeout = setTimeout(() => reject(new Error('A janela não produziu imagens. Confira se está visível e não minimizada.')), 8000);
        const cancelFrame = () => { clearTimeout(timeout); reject(new DOMException('Captura cancelada', 'AbortError')); };
        signal.addEventListener('abort', cancelFrame, { once: true });
        resources.push(() => { clearTimeout(timeout); signal.removeEventListener('abort', cancelFrame); });
        ws.onclose = () => { clearTimeout(timeout); if (!initialized) reject(new Error('A captura foi encerrada.')); else if (!stopped) onEnded(); };
        ws.onmessage = async event => {
          if (decoding || stopped || !(event.data instanceof ArrayBuffer)) return;
          decoding = true;
          try {
            const bitmap = await createImageBitmap(new Blob([event.data], { type: 'image/jpeg' }));
            if (stopped || signal.aborted) { bitmap.close(); return; }
            if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) { canvas.width = bitmap.width; canvas.height = bitmap.height; }
            context.drawImage(bitmap, 0, 0); bitmap.close();
            if (!initialized) {
              initialized = true; clearTimeout(timeout);
              const result = canvas.captureStream(captureFps(options.quality.fps));
              result.getVideoTracks()[0].contentHint = options.quality.preference;
              resolve(result);
            }
          } catch (error) { console.warn('[Capture] Frame descartado:', error); }
          finally { decoding = false; }
        };
      });
      check();
      if (options.audio !== 'none') {
        const pid = options.audio === 'process' ? options.process?.Pid : 0;
        if (pid === undefined) throw new Error('Selecione o processo do áudio.');
        if (await api.StartProcessAudioCapture(pid)) {
          check();
          const format: { sampleRate: number; channels: number } = JSON.parse(await api.GetProcessAudioFormat());
          const audio = new AudioContext();
          resources.push(() => audio.close()); await audio.resume(); check();
          const destination = audio.createMediaStreamDestination();
          const socket = await openSocket('ws://127.0.0.1:59123/audiostream', signal);
          resources.push(() => socket.close()); check();
          let sampleRate = format.sampleRate; let channels = format.channels;
          let next = audio.currentTime + 0.04;
          const scheduled = new Set<AudioBufferSourceNode>();
          resources.push(() => { scheduled.forEach(node => { node.stop(); node.disconnect(); }); scheduled.clear(); });
          socket.onmessage = event => {
            if (stopped || audio.state === 'closed') return;
            if (typeof event.data === 'string') {
              try {
                const value: unknown = JSON.parse(event.data);
                if (value && typeof value === 'object' && 'sampleRate' in value && 'channels' in value &&
                  typeof value.sampleRate === 'number' && value.sampleRate >= 8000 && value.sampleRate <= 192000 &&
                  typeof value.channels === 'number' && value.channels >= 1 && value.channels <= 8) {
                  sampleRate = value.sampleRate; channels = value.channels;
                }
              } catch (error) { console.warn('[Capture] Formato de áudio inválido:', error); }
              return;
            }
            if (!(event.data instanceof ArrayBuffer) || !event.data.byteLength || event.data.byteLength % (4 * channels)) return;
            // Keep at most 180 ms queued; never overlap old buffers after a stalled connection.
            if (next > audio.currentTime + 0.18) return;
            const samples = new Float32Array(event.data);
            const frames = samples.length / channels;
            const buffer = audio.createBuffer(channels, frames, sampleRate);
            for (let channel = 0; channel < channels; channel++) {
              const output = buffer.getChannelData(channel);
              for (let frame = 0; frame < frames; frame++) output[frame] = samples[frame * channels + channel];
            }
            const node = audio.createBufferSource(); node.buffer = buffer; node.connect(destination); scheduled.add(node);
            node.onended = () => { scheduled.delete(node); node.disconnect(); };
            next = Math.max(next, audio.currentTime + 0.015); node.start(next); next += buffer.duration;
          };
          stream.addTrack(destination.stream.getAudioTracks()[0]);
        } else warning = 'O áudio não pôde ser capturado. A tela está sendo compartilhada sem som.';
      }
    }
    check();
    if (options.audio !== 'none' && !stream.getAudioTracks().length) warning = warning || 'A fonte escolhida não forneceu áudio. No navegador, marque a opção de compartilhar áudio quando disponível.';
    stream.getVideoTracks()[0].addEventListener('ended', () => { if (!stopped) onEnded(); }, { once: true });
    signal.removeEventListener('abort', abort);
    signal.addEventListener('abort', () => { void stop(); }, { once: true });
    return { stream, source: options.source === 'camera' ? 'Câmera' : options.source === 'browser' ? 'Navegador' : 'Windows', warning, stop };
  } catch (error) { await stop(); throw error; }
}
