/** The worker starts asynchronously. Retry connection refusals until ready or cancelled. */
export function openCaptureSocket(url: string, signal: AbortSignal, timeoutMs = 15000, retryMs = 150,
  checkWorker?: () => Promise<void>): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let attemptTimer: ReturnType<typeof setTimeout> | undefined;
    let finished = false;
    const discard = () => {
      clearTimeout(attemptTimer);
      if (socket) {
        socket.onopen = socket.onerror = socket.onclose = null;
        socket.close(); socket = undefined;
      }
    };
    const finish = (error?: Error) => {
      if (finished) return;
      finished = true; clearTimeout(deadline); clearTimeout(retry); clearTimeout(attemptTimer);
      signal.removeEventListener('abort', abort);
      if (error) { discard(); reject(error); }
      else { const opened = socket!; opened.onopen = opened.onerror = opened.onclose = null; resolve(opened); }
    };
    const abort = () => finish(new DOMException('Captura cancelada', 'AbortError'));
    const deadline = setTimeout(() => finish(new Error('A captura local não respondeu. Confira se o processo auxiliar iniciou.')), timeoutMs);
    const attempt = async () => {
      if (finished) return;
      if (signal.aborted) { abort(); return; }
      try { await checkWorker?.(); }
      catch { finish(new Error('O processo auxiliar de captura encerrou antes de conectar. Tente novamente.')); return; }
      if (finished) return;
      if (signal.aborted) { abort(); return; }
      const failed = () => {
        if (finished || retry !== undefined) return;
        discard();
        retry = setTimeout(() => { retry = undefined; attempt(); }, retryMs);
      };
      try {
        socket = new WebSocket(url); socket.binaryType = 'arraybuffer';
        socket.onopen = () => signal.aborted ? abort() : finish();
        socket.onerror = socket.onclose = failed;
        attemptTimer = setTimeout(failed, 1500);
      } catch { failed(); }
    };
    signal.addEventListener('abort', abort, { once: true });
    attempt();
  });
}
