import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { RoomClient, type LocalPublication } from './RoomClient';
import { MAX_LOCAL_STREAMS } from './protocol';
import { startCapture, type CaptureHandle, type CaptureOptions } from './capture';
export interface LocalCapture extends LocalPublication { source: CaptureOptions['source'] }
export function useRoom() {
  const [client] = useState(() => new RoomClient());
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot);
  const handles = useRef(new Map<string, CaptureHandle>());
  const controller = useRef<AbortController | undefined>(undefined);
  const [locals, setLocals] = useState<LocalCapture[]>([]);
  const [capturing, setCapturing] = useState(false);
  const [captureError, setCaptureError] = useState('');
  const [warning, setWarning] = useState('');
  const generation = useRef(0);
  const stop = async (id: string) => {
    const current = handles.current.get(id); handles.current.delete(id);
    client.removeLocal(id); setLocals(items => items.filter(item => item.id !== id)); await current?.stop();
  };
  const cancel = () => { generation.current++; controller.current?.abort(); controller.current = undefined; setCapturing(false); };
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
    try {
      const capture = await startCapture(options, abort.signal, () => { void stop(id); });
      if (currentGeneration !== generation.current || abort.signal.aborted || !['connected', 'reconnecting'].includes(client.getSnapshot().phase)) { await capture.stop(); return; }
      const publication: LocalCapture = { id, title: title.trim().slice(0, 80) || (options.source === 'camera' ? 'Câmera' : 'Tela'),
        kind: options.source === 'camera' ? 'camera' : 'screen', stream: capture.stream, quality: options.quality, source: options.source };
      handles.current.set(id, capture); client.addLocal(publication);
      setLocals(items => [...items, publication]); setWarning(capture.warning);
    } catch (error) {
      if (currentGeneration === generation.current && !abort.signal.aborted) setCaptureError(error instanceof Error ? error.message : 'Falha ao compartilhar.');
    } finally { if (currentGeneration === generation.current) { controller.current = undefined; setCapturing(false); } }
  };
  useEffect(() => {
    const cleanup = () => { generation.current++; controller.current?.abort(); handles.current.forEach(handle => { void handle.stop(); }); handles.current.clear(); client.leave(); };
    window.addEventListener('pagehide', cleanup);
    return () => { window.removeEventListener('pagehide', cleanup); cleanup(); };
  }, [client]);
  useEffect(() => {
    if (!['idle', 'closed', 'error'].includes(state.phase)) return;
    generation.current++; controller.current?.abort(); controller.current = undefined;
    handles.current.forEach(handle => { void handle.stop(); }); handles.current.clear();
    setLocals([]); setCapturing(false);
  }, [state.phase]);
  const leave = async () => { await stopAll(); client.leave(); };
  return { client, state, locals, capturing, captureError, warning, share, stop, stopAll, cancel, leave };
}
