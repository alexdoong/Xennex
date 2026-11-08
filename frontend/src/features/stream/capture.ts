import { LatestCaptureFrame } from './latestFrame';
import { CaptureOutputError } from './captureVideoOutput';
import { createCaptureFramePipeline, type CaptureFrameMode } from './captureFramePipeline';
import { browserCaptureStatus, screenCaptureExplanation, screenCaptureFailure } from './browserCaptureSupport';
import { parseCaptureMetrics, CaptureFrameTimings, type CapturePipeline } from './captureMetrics';
import { openCaptureSocket } from './captureSocket';
import { captureAwait, waitCaptureState, parseCaptureState, type CapturePhase } from './captureStartup';
import { QUALITY_PRESETS, captureFps, requestedFps, fitWithin, type Quality } from './quality';
export type NativeApi = Window['chrome']['webview']['hostObjects']['api'];
export interface AudioProcess { Pid: number; Hwnd: number; Name: string; Title: string; HasActiveAudio: boolean; PeakVolume: number }
export interface CaptureMonitor { Id: string; Width: number; Height: number; Primary: boolean }
export interface CaptureOptions { source: 'browser' | 'window' | 'monitor' | 'camera' | 'game'; monitorBackend?: 'wgc' | 'dxgi'; monitorId?: string; cameraId?: string; audioDeviceId?: string; frameOutput?: CaptureFrameMode; process?: AudioProcess; audioProcess?: AudioProcess; audio: 'none' | 'window' | 'system' | 'process' | 'microphone' | 'device'; quality: Quality }
export interface CaptureHandle { stream: MediaStream; source: string; nativeSession: boolean; warning: string; readonly pipeline?: CapturePipeline; stop(): Promise<void> }
export interface CaptureEvents { onProgress?: (phase: CapturePhase) => void; onWarning?: (message: string) => void; onMetrics?: (metrics: CapturePipeline) => void }
export const nativeApi = (): NativeApi | undefined => window.chrome?.webview?.hostObjects?.api;

type BrowserDisplayOptions = DisplayMediaStreamOptions & {
  windowAudio?: 'window' | 'system' | 'exclude';
  systemAudio?: 'include' | 'exclude';
  selfBrowserSurface?: 'include' | 'exclude';
};

export function browserDisplayOptions(options: CaptureOptions, restrictOwnAudioSupported: boolean): BrowserDisplayOptions {
  const browserAudio = options.audio === 'system' || options.audio === 'window';
  const windowOnly = options.audio === 'window';
  const hasFps = requestedFps(options.quality.fps);
  const fpsConstraint = hasFps ? { frameRate: { ideal: captureFps(options.quality.fps), max: captureFps(options.quality.fps) } } : {};
  const video = windowOnly
    ? { displaySurface: 'window' as const, ...fpsConstraint }
    : (hasFps ? fpsConstraint : true);
  return {
    video,
    audio: !browserAudio ? false : {
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      ...(restrictOwnAudioSupported ? { restrictOwnAudio: true } : {}),
    },
    ...(!browserAudio ? {} : windowOnly
      ? { windowAudio: 'window' as const, systemAudio: 'exclude' as const, selfBrowserSurface: 'exclude' as const }
      : { windowAudio: 'window' as const, systemAudio: 'include' as const }),
  };
}

export async function startCapture(options: CaptureOptions, signal: AbortSignal, onEnded: () => void, events: CaptureEvents = {}): Promise<CaptureHandle> {
  const api = nativeApi();
  if (options.source === 'monitor' && options.monitorBackend === 'dxgi' && !options.monitorId)
    throw new Error('Escolha o monitor que contém o jogo.');
  if (options.audio === 'process' &&
      !(options.audioProcess?.Pid || ((options.source === 'window' || options.source === 'game') && options.process?.Pid))) {
    throw new Error('Selecione a janela ou processo que fornecerá o áudio.');
  }
  const owner = crypto.randomUUID();
  const resources: (() => void | Promise<void>)[] = [];
  let stopped = false;
  let stream: MediaStream | undefined;
  let warning = '';
  let pipeline: CapturePipeline | undefined;
  const timings = new CaptureFrameTimings();
  let nativeOwned = false;
  let token = '';
  const progress = (phase: CapturePhase) => events.onProgress?.(phase);
  const warn = (message: string) => { warning = message; if (!stopped && !signal.aborted) events.onWarning?.(message); };
  const nativeCall = <T,>(promise: PromiseLike<T>, late?: (value: T) => void | Promise<void>) =>
    captureAwait(promise, signal, 10000, 'O aplicativo não respondeu ao iniciar a captura. Tente novamente.', late);
  const stop = async () => {
    if (stopped) return; stopped = true;
    progress('stopping');
    signal.removeEventListener('abort', abort);
    stream?.getTracks().forEach(track => track.stop());
    for (const release of resources.reverse()) { try { await release(); } catch (error) { console.warn('[Capture] Limpeza:', error); } }
  };
  const abort = () => { stream?.getTracks().forEach(track => track.stop()); };
  const check = () => { if (signal.aborted || stopped) throw new DOMException('Captura cancelada', 'AbortError'); };
  const acquireNative = async () => {
    if (!api) throw new Error('Áudio por processo disponível apenas no aplicativo.');
    token = encodeURIComponent(await nativeCall(api.GetCaptureToken())); check();
    const acquired = await nativeCall(api.TryBeginCapture(owner), async value => { if (value) await api.EndCapture(owner); });
    if (!acquired) throw new Error('Outra captura do Xennex já usa o áudio por processo ou o vídeo nativo. Pare essa captura primeiro.');
    if (signal.aborted || stopped) { await api.EndCapture(owner); check(); }
    nativeOwned = true;
    resources.push(async () => {
      await captureAwait(api.EndCapture(owner), new AbortController().signal, 3000, 'A captura ainda está sendo encerrada.');
      await waitCaptureState(() => api.GetCaptureState(owner), 'phase', 'idle', new AbortController().signal, 7000);
    });
    window.chrome.webview.postMessage(`capture-owner:${owner}`);
  };
  signal.addEventListener('abort', abort, { once: true });
  try {
    check();
    if (options.source === 'camera') {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Câmera indisponível. Abra em HTTPS ou no aplicativo.');
      const preset = QUALITY_PRESETS[options.quality.resolution];
      progress('selecting');
      stream = await captureAwait(navigator.mediaDevices.getUserMedia({
        video: { ...(options.cameraId ? { deviceId: { exact: options.cameraId } } : {}),
          ...(preset.width ? { width: { ideal: preset.width }, height: { ideal: preset.height } } : {}),
          ...(requestedFps(options.quality.fps) ? { frameRate: { ideal: captureFps(options.quality.fps), max: captureFps(options.quality.fps) } } : {}) },
        audio: options.audio === 'microphone' ? { echoCancellation: true, noiseSuppression: true } : false,
      }), signal, 30000, 'A câmera não respondeu. Confira a permissão e tente novamente.', value => value.getTracks().forEach(track => track.stop()));
      if (signal.aborted || stopped) { stream.getTracks().forEach(track => track.stop()); check(); }
      stream.getVideoTracks()[0].contentHint = options.quality.preference;
    } else if (options.source === 'browser') {
      const browserSupport = browserCaptureStatus();
      if (browserSupport.screen !== 'available') throw new Error(screenCaptureExplanation(browserSupport));
      // Request during the click gesture, before any network/native await.
      const supported = navigator.mediaDevices.getSupportedConstraints?.() as (MediaTrackSupportedConstraints & { restrictOwnAudio?: boolean }) | undefined;
      progress('selecting');
      try {
        stream = await captureAwait(navigator.mediaDevices.getDisplayMedia(browserDisplayOptions(options, !!supported?.restrictOwnAudio)),
          signal, 120000, 'O seletor de tela não foi confirmado. Tente novamente e escolha a fonte na janela do navegador.', value => value.getTracks().forEach(track => track.stop()));
      } catch (error) {
        const explanation = screenCaptureFailure(error);
        if (explanation) throw new Error(explanation, { cause: error });
        throw error;
      }
      if (signal.aborted || stopped) { stream.getTracks().forEach(track => track.stop()); check(); }
      const track = stream.getVideoTracks()[0];
      progress('video');
      if (!track) throw new Error('Nenhuma tela foi selecionada.');
      const preset = QUALITY_PRESETS[options.quality.resolution];
      track.contentHint = options.quality.preference;
      {
        const settings = track.getSettings();
        const size = fitWithin(settings.width || preset.width, settings.height || preset.height, preset.width, preset.height);
        try { await nativeCall(track.applyConstraints({
          ...(size.width ? { width: { ideal: size.width, max: size.width }, height: { ideal: size.height, max: size.height } } : {}),
          ...(requestedFps(options.quality.fps) ? { frameRate: { ideal: captureFps(options.quality.fps), max: captureFps(options.quality.fps) } } : {}),
        })); }
        catch { warning = 'O navegador manteve o formato disponível da fonte. Confira as medidas na prévia.'; }
        const actual = track.getSettings();
        if (size.width && actual.width && actual.height && (actual.width < size.width * .95 || actual.height < size.height * .95)) {
          warning = [warning, `A fonte foi configurada em ${actual.width} × ${actual.height}, abaixo do tamanho solicitado. Confira a captura antes de aumentar a qualidade.`].filter(Boolean).join(' ');
        }
        if (requestedFps(options.quality.fps) && actual.frameRate && actual.frameRate < options.quality.fps * .9) {
          warning = [warning, `O limite disponível na captura é ${Math.round(actual.frameRate)} FPS; o alvo escolhido foi ${options.quality.fps} FPS.`].filter(Boolean).join(' ');
        }
        if (settings.displaySurface === 'monitor' && stream.getAudioTracks().length) {
          const audioSettings = stream.getAudioTracks()[0].getSettings() as MediaTrackSettings & { restrictOwnAudio?: boolean };
          const echoWarning = audioSettings.restrictOwnAudio
            ? 'O navegador tenta excluir o som desta aba, mas chamadas em outros aplicativos ou abas ainda podem entrar no áudio da tela inteira.'
            : 'O áudio da tela inteira pode incluir a voz da chamada e causar eco. Prefira áudio de uma aba ou janela isolada.';
          warning = [warning, echoWarning].filter(Boolean).join(' ');
        }
      }
      if (options.audio === 'process') {
        await acquireNative(); check();
        if (!await nativeCall(api!.BeginBrowserCapture(owner))) throw new Error('Não foi possível preparar o áudio desta transmissão.');
      } else if (options.audio === 'device') {
        if (!navigator.mediaDevices?.getUserMedia) {
          warn('Canal de entrada de áudio indisponível neste navegador. A tela está sendo compartilhada sem som.');
        } else {
          progress('audio');
          try {
            const deviceAudio = await captureAwait(
              navigator.mediaDevices.getUserMedia({
                video: false,
                audio: {
                  ...(options.audioDeviceId ? { deviceId: { exact: options.audioDeviceId } } : {}),
                  echoCancellation: false,
                  noiseSuppression: false,
                  autoGainControl: false,
                },
              }),
              signal,
              20000,
              'O canal de áudio não respondeu. Confira a permissão e tente novamente.',
              value => value.getTracks().forEach(t => t.stop()),
            );
            check();
            resources.push(() => deviceAudio.getTracks().forEach(t => t.stop()));
            const audioTrack = deviceAudio.getAudioTracks()[0];
            if (audioTrack) stream.addTrack(audioTrack);
          } catch (error) {
            check();
            warn(`${error instanceof Error ? error.message : 'O canal de áudio não pôde ser capturado.'} A tela está sendo compartilhada sem som.`);
          }
        }
      }
    } else {
      if (!api) throw new Error('Captura nativa disponível apenas no aplicativo.');
      if ((options.source === 'window' || options.source === 'game') && !options.process?.Hwnd) throw new Error('Selecione uma janela antes de compartilhar.');
      progress('video');
      await acquireNative(); check();
      const desktop = options.source === 'monitor' && options.monitorBackend === 'dxgi';
      const game = options.source === 'game';
      const started = await nativeCall(game
        ? api.BeginGameCapture(owner, options.process!.Hwnd, options.process!.Pid, captureFps(options.quality.fps), options.quality.resolution)
        : desktop
        ? api.BeginDesktopCapture(owner, options.monitorId!, captureFps(options.quality.fps), options.quality.resolution)
        : api.BeginNativeCapture(owner, options.source === 'window' ? options.process!.Hwnd : 0,
          options.process?.Pid || 0, captureFps(options.quality.fps), options.quality.resolution));
      check();
      if (!started) throw new Error('A captura nativa não iniciou. Tente a opção de seleção pelo navegador.');
      await waitCaptureState(() => api.GetCaptureState(owner), 'video', 'ready', signal, 10000);
      const ws = await openCaptureSocket(`ws://127.0.0.1:59124/videostream/?token=${token}`, signal, 15000, 150, async () => {
        const state = parseCaptureState(await nativeCall(api.GetCaptureState(owner)));
        if (state.phase !== 'active' || state.video !== 'ready') throw new Error('Capture worker stopped');
      });
      resources.push(() => ws.close()); check();
      // Keep canvas as default until the optional output is measured successfully
      // in WebView2 across foreground, background and restoration.
      const output = createCaptureFramePipeline(captureFps(options.quality.fps), options.quality.preference, options.frameOutput);
      resources.push(() => output.stop());
      progress('frame');
      stream = await new Promise<MediaStream>((resolve, reject) => {
        let initialized = false;
        let recoveryMessage = '';
        let instabilityMessage = '';
        const timeout = setTimeout(() => reject(new Error(game ? 'O jogo não produziu imagens OpenGL. Volte ao jogo ou use outro método de captura.' : desktop ? 'O monitor não produziu imagens. Confira se ele está conectado e se o Windows terminou a troca de modo.' : 'A janela não produziu imagens. Confira se está visível e não minimizada.')), game ? 30000 : desktop ? 20000 : 8000);
        const cancelFrame = () => { clearTimeout(timeout); output.stop(); reject(new DOMException('Captura cancelada', 'AbortError')); };
        signal.addEventListener('abort', cancelFrame, { once: true });
        resources.push(() => { clearTimeout(timeout); signal.removeEventListener('abort', cancelFrame); });
        ws.onclose = () => { clearTimeout(timeout); frames.stop(); output.stop(); if (!initialized) reject(new Error('A captura foi encerrada.')); else if (!stopped) onEnded(); };
        ws.onerror = () => { if (!initialized) { clearTimeout(timeout); reject(new Error('A conexão com a captura de vídeo falhou. Tente novamente.')); } };
        resources.push(() => { ws.onmessage = ws.onclose = ws.onerror = null; });
        const frames = new LatestCaptureFrame(async (data, receivedAt) => {
          if (stopped || signal.aborted) return;
          const decodeStart = performance.now();
          const measured = await output.write(data);
          timings.add(measured.decodeMs, measured.submitMs, decodeStart - receivedAt + measured.communicationMs);
          if (stopped || signal.aborted) return;
          if (!initialized) {
            initialized = true; clearTimeout(timeout);
            resolve(output.stream);
          }
        }, () => timings.dropped(), error => {
          console.warn('[Capture] Frame descartado:', error);
          if (initialized && error instanceof CaptureOutputError && !stopped) {
            warn(error.message); void stop(); onEnded();
          }
        });
        resources.push(() => frames.stop());
        ws.onmessage = async event => {
          if (stopped) return;
          if (typeof event.data === 'string') {
            const metrics = parseCaptureMetrics(event.data);
            if (metrics) {
              pipeline = { worker: metrics, receivedAt: Date.now(), ...timings.take(output.path === 'canvas' ? 'canvas' : 'generator'), decoder: output.decoder, output: output.path };
              events.onMetrics?.(pipeline);
              return;
            }
            if (!desktop || event.data.length > 4096) return;
            try {
              const status: unknown = JSON.parse(event.data);
              if (status && typeof status === 'object' && 'type' in status && status.type === 'capture-status' && 'phase' in status) {
                if (status.phase === 'recovering') {
                  recoveryMessage = 'Recuperando a captura do monitor após troca de tela cheia ou modo de vídeo…';
                  if (!warning.includes(recoveryMessage)) warn([warning, recoveryMessage].filter(Boolean).join(' '));
                } else if (status.phase === 'unstable') {
                  instabilityMessage = 'O Windows está invalidando esta captura repetidamente. Em jogos como osu! em tela cheia exclusiva, tente janela/sem bordas ou outra fonte de captura.';
                  if (!warning.includes(instabilityMessage)) warn([warning.replace(recoveryMessage, '').trim(), instabilityMessage].filter(Boolean).join(' '));
                } else if (status.phase === 'ready' && (recoveryMessage || instabilityMessage)) {
                  warn(warning.replace(recoveryMessage, '').replace(instabilityMessage, '').trim());
                  recoveryMessage = instabilityMessage = '';
                }
              }
            } catch { /* Ignore unsupported status messages, never arbitrary worker text. */ }
            return;
          }
          if (!(event.data instanceof ArrayBuffer)) return;
          timings.arrived();
          await frames.push(event.data);
        };
      });
      check();
    }
    if (nativeOwned && api && options.audio !== 'none') {
      progress('audio');
      const pid = options.audio === 'process' ? (options.audioProcess?.Pid || options.process?.Pid) : 0;
      if (pid === undefined) throw new Error('Selecione o processo do áudio.');
      const audioResources = resources.length;
      try {
        if (!await nativeCall(api.BeginCaptureAudio(owner, pid))) throw new Error('O áudio não pôde ser iniciado.');
        await waitCaptureState(() => api.GetCaptureState(owner), 'audio', 'ready', signal, 6000);
        check();
        const format: { sampleRate: number; channels: number } = JSON.parse(await nativeCall(api.GetProcessAudioFormat()));
        const audio = new AudioContext();
        resources.push(() => audio.state === 'closed' ? undefined : audio.close()); await nativeCall(audio.resume()); check();
        const destination = audio.createMediaStreamDestination();
        const socket = await openCaptureSocket(`ws://127.0.0.1:59123/audiostream?token=${token}`, signal);
        resources.push(() => socket.close()); check();
        let sampleRate = format.sampleRate; let channels = format.channels;
        let next = audio.currentTime + 0.04;
        const scheduled = new Set<AudioBufferSourceNode>();
        resources.push(() => { scheduled.forEach(node => { node.stop(); node.disconnect(); }); scheduled.clear(); });
        let audioLost = false; let checking = false;
        const lost = () => {
          if (audioLost || stopped || signal.aborted) return;
          audioLost = true;
          destination.stream.getAudioTracks().forEach(track => track.stop());
          scheduled.forEach(node => { node.stop(); node.disconnect(); }); scheduled.clear();
          socket.onmessage = socket.onclose = socket.onerror = null;
          socket.close(); clearInterval(health);
          void audio.close().catch(error => console.warn('[Capture] Áudio:', error));
          void nativeCall(api.StopCaptureAudio(owner)).catch(error => console.warn('[Capture] Parar áudio:', error));
          warn('O áudio foi interrompido. O vídeo continua; pare e reinicie esta transmissão para recuperar o som.');
        };
        socket.onclose = socket.onerror = lost;
        // A process may become silent legitimately; check worker state, not sample silence.
        const health = setInterval(async () => {
          if (checking || audioLost || stopped) return;
          checking = true;
          try {
            const state = parseCaptureState(await nativeCall(api.GetCaptureState(owner)));
            if (state.audio !== 'ready') lost();
          } catch { lost(); }
          finally { checking = false; }
        }, 1000);
        resources.push(() => { clearInterval(health); socket.onclose = socket.onerror = null; });
        socket.onmessage = event => {
          if (audioLost || stopped || audio.state === 'closed') return;
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
      } catch (error) {
        check();
        for (const release of resources.splice(audioResources).reverse()) {
          try { await release(); } catch (cleanupError) { console.warn('[Capture] Limpeza de áudio:', cleanupError); }
        }
        await nativeCall(api.StopCaptureAudio(owner));
        warn(`${error instanceof Error ? error.message : 'O áudio não pôde ser capturado.'} A tela está sendo compartilhada sem som.`);
      }
    }
    check();
    if (options.audio !== 'none' && !stream.getAudioTracks().length) {
      warning = warning || (options.source === 'browser' && options.audio === 'window'
        ? 'A janela selecionada não forneceu áudio. No Chrome, Brave ou Opera GX, escolha a aba Janela e marque "Compartilhar também o áudio da janela".'
        : 'A fonte escolhida não forneceu áudio. No navegador, marque a opção de compartilhar áudio quando disponível.');
    }
    stream.getVideoTracks()[0].addEventListener('ended', () => { if (!stopped) onEnded(); }, { once: true });
    signal.removeEventListener('abort', abort);
    signal.addEventListener('abort', () => { void stop(); }, { once: true });
    return { stream, source: options.source === 'camera' ? 'Câmera' : options.source === 'browser' ? 'Navegador' : 'Windows', nativeSession: nativeOwned, get warning() { return warning; }, get pipeline() { return pipeline; }, stop };
  } catch (error) { await stop(); throw error; }
}
