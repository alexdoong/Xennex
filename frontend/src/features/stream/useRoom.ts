import type { CapturePipeline } from './captureMetrics';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { RoomClient, type LocalPublication } from './RoomClient';
import { MAX_LOCAL_STREAMS } from './protocol';
import { startCapture, type CaptureHandle, type CaptureOptions } from './capture';
import { type CapturePhase } from './captureStartup';
import { useStreamAnnouncements } from './useStreamAnnouncements';
export interface LocalCapture extends LocalPublication { source: CaptureOptions['source']; nativeSession: boolean; warning?: string; pipeline?: CapturePipeline }
export function useRoom() {
  const [client] = useState(() => new RoomClient());
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot);
  const newScreens = useStreamAnnouncements(state, client.sessionId);
  const handles = useRef(new Map<string, CaptureHandle>());
  const controller = useRef<AbortController | undefined>(undefined);
  const [locals, setLocals] = useState<LocalCapture[]>([]);
  const [capturing, setCapturing] = useState(false);
  const [capturePhase, setCapturePhase] = useState<CapturePhase>('selecting');
  const [captureError, setCaptureError] = useState('');
  const [warning, setWarning] = useState('');
  const generation = useRef(0);
  const stop = async (id: string) => {
    const current = handles.current.get(id); handles.current.delete(id);
    client.removeLocal(id); setLocals(items => items.filter(item => item.id !== id)); await current?.stop();
  };
  const cancel = () => { generation.current++; if (controller.current) setCapturePhase('stopping'); controller.current?.abort(); };
  const stopAll = async () => {
    cancel(); const current = [...handles.current.entries()]; handles.current.clear();
    current.forEach(([id]) => client.removeLocal(id)); setLocals([]); setWarning('');
    await Promise.all(current.map(([, handle]) => handle.stop()));
  };
  const share = async (options: CaptureOptions, title: string) => {
    if (controller.current || handles.current.size >= MAX_LOCAL_STREAMS || client.getSnapshot().phase !== 'connected') return;
    const currentGeneration = ++generation.current;
    const abort = new AbortController(); controller.current = abort;
    const id = crypto.randomUUID();
    setCapturing(true); setCaptureError(''); setWarning('');
    setCapturePhase(options.source === 'browser' || options.source === 'camera' ? 'selecting' : 'video');
    const deadline = setTimeout(() => abort.abort(), options.source === 'browser' ? 150000 : 45000);
    let timedOut = false;
    const timeoutNotice = () => { timedOut = true; };
    // The deadline is separate from user cancellation, which increments generation.
    abort.signal.addEventListener('abort', timeoutNotice, { once: true });
    let pending: CaptureHandle | undefined;
    let endedBeforePublish = false;
    try {
      const capture = await startCapture(options, abort.signal, () => {
        if (handles.current.has(id)) void stop(id);
        else endedBeforePublish = true;
      }, {
        onProgress: phase => { if (controller.current === abort && currentGeneration === generation.current) setCapturePhase(phase); },
        onMetrics: pipeline => {
          if (handles.current.has(id)) setLocals(items => items.map(item => item.id === id ? { ...item, pipeline } : item));
        },
        onWarning: message => {
          if (handles.current.has(id)) setLocals(items => items.map(item => item.id === id ? { ...item, warning: message } : item));
          if (currentGeneration === generation.current || handles.current.has(id)) setWarning(message);
        },
      });
      pending = capture;
      if (endedBeforePublish || capture.stream.getVideoTracks().some(track => track.readyState === 'ended')) {
        throw new Error('A fonte encerrou durante a inicialização. Selecione uma janela visível e tente novamente.');
      }
      if (currentGeneration !== generation.current || abort.signal.aborted || !['connected', 'reconnecting'].includes(client.getSnapshot().phase)) { await capture.stop(); return; }
      const publication: LocalCapture = { id, title: title.trim().slice(0, 80) || (options.source === 'camera' ? 'Câmera' : 'Tela'),
        kind: options.source === 'camera' ? 'camera' : 'screen', stream: capture.stream, quality: options.quality, source: options.source, nativeSession: capture.nativeSession, warning: capture.warning, pipeline: capture.pipeline };
      setCapturePhase('publishing');
      handles.current.set(id, capture); client.addLocal(publication);
      setLocals(items => [...items, publication]); setWarning(capture.warning); pending = undefined;
    } catch (error) {
      handles.current.delete(id); client.removeLocal(id); await pending?.stop();
      if (currentGeneration === generation.current && !abort.signal.aborted) setCaptureError(error instanceof Error ? error.message : 'Falha ao compartilhar.');
      else if (currentGeneration === generation.current && timedOut) setCaptureError('A captura demorou demais e foi cancelada. Confira a fonte e tente novamente.');
    } finally {
      clearTimeout(deadline); abort.signal.removeEventListener('abort', timeoutNotice);
      if (controller.current === abort) { controller.current = undefined; setCapturing(false); }
    }
  };
  useEffect(() => {
    const cleanup = () => { generation.current++; controller.current?.abort(); handles.current.forEach(handle => { void handle.stop(); }); handles.current.clear(); client.leave(); };
    window.addEventListener('pagehide', cleanup);
    return () => { window.removeEventListener('pagehide', cleanup); cleanup(); };
  }, [client]);
  useEffect(() => {
    if (!['idle', 'closed', 'error'].includes(state.phase)) return;
    generation.current++; controller.current?.abort();
    handles.current.forEach(handle => { void handle.stop(); }); handles.current.clear();
    setLocals([]);
  }, [state.phase]);
  const leave = async () => { await stopAll(); client.leave(); };
  return { client, state, newScreens, locals, capturing, capturePhase, captureError, warning, share, stop, stopAll, cancel, leave };
}
