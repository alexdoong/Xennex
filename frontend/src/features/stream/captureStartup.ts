export type CapturePhase = 'selecting' | 'video' | 'frame' | 'audio' | 'publishing' | 'stopping';
export const CAPTURE_PHASE_LABELS: Record<CapturePhase, string> = {
  selecting: 'Escolha a fonte e confirme a permissão na janela do navegador.',
  video: 'Iniciando a captura de vídeo…',
  frame: 'Aguardando a primeira imagem. Mantenha a janela visível.',
  audio: 'Preparando o áudio da transmissão…',
  publishing: 'Adicionando a transmissão à sala…',
  stopping: 'Cancelando e liberando a captura…',
};

/** A native call or permission prompt may settle late. Release late acquisitions. */
export function captureAwait<T>(operation: PromiseLike<T>, signal: AbortSignal, timeoutMs: number,
  message: string, releaseLate?: (value: T) => void | Promise<void>): Promise<T> {
  return new Promise((resolve, reject) => {
    let finished = false;
    const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); };
    const fail = (error: Error) => { if (finished) return; finished = true; cleanup(); reject(error); };
    const abort = () => fail(new DOMException('Captura cancelada', 'AbortError'));
    const timer = setTimeout(() => fail(new Error(message)), timeoutMs);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    Promise.resolve(operation).then(value => {
      if (finished) { void Promise.resolve().then(() => releaseLate?.(value)).catch(error => console.warn('[Capture] Limpeza tardia:', error)); return; }
      finished = true; cleanup(); resolve(value);
    }, error => fail(error instanceof Error ? error : new Error(String(error))));
  });
}

export interface NativeCaptureState { phase: 'idle' | 'active' | 'stopping'; video: string; audio: string }
export function parseCaptureState(value: string): NativeCaptureState {
  const state: unknown = JSON.parse(value);
  if (!state || typeof state !== 'object' || !('phase' in state) || !['idle', 'active', 'stopping'].includes(String(state.phase)) ||
      !('video' in state) || typeof state.video !== 'string' || !('audio' in state) || typeof state.audio !== 'string') {
    throw new Error('O app não retornou um estado de captura válido. Atualize o aplicativo.');
  }
  return state as NativeCaptureState;
}

export async function waitCaptureState(read: () => Promise<string>, field: 'video' | 'audio' | 'phase',
  target: string, signal: AbortSignal, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const message = field === 'audio' ? 'O áudio não iniciou a tempo. Tente novamente ou compartilhe sem áudio.'
    : 'A captura não respondeu a tempo. Confira a janela escolhida e tente novamente.';
  while (Date.now() < deadline) {
    const state = parseCaptureState(await captureAwait(read(), signal, Math.max(1, deadline - Date.now()), message));
    if (state[field] === target) return;
    if (field !== 'phase' && (state[field] === 'error' || state.phase !== 'active')) {
      throw new Error(field === 'video' ? 'O processo de captura não iniciou ou foi encerrado. Confira se a janela está aberta e não minimizada; tente novamente.' : message);
    }
    await captureAwait(new Promise<void>(resolve => setTimeout(resolve, 100)), signal, Math.max(1, deadline - Date.now()), message);
  }
  throw new Error(message);
}
