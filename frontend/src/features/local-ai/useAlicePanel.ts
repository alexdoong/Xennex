import { useCallback, useEffect, useRef, useState } from 'react';
import type { AliceAction, AliceFrame, AliceModality, AliceSettings, AliceState } from './aliceTypes';

export default function useAlicePanel(active: boolean) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api);
  const [state, setState] = useState<AliceState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const refresh = useCallback(async () => {
    if (!api.current) throw Error('Abra este painel no Xennex para conectar a Alice.');
    const value = JSON.parse(await api.current.GetAliceState()) as AliceState;
    setState(value);
  }, []);
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { if (!locked.current) await refresh(); }
      catch (reason) { if (!cancelled) setError(String(reason)); }
      if (!cancelled) timer = setTimeout(poll, 1500);
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [active, refresh]);
  const run = async <T,>(work: () => Promise<T>): Promise<T | null> => {
    if (locked.current) return null;
    locked.current = true; setBusy(true); setError('');
    try {
      const result = await work();
      try { await refresh(); } catch (reason) { setError('A operação foi enviada, mas o estado não pôde ser atualizado: ' + String(reason)); }
      return result;
    }
    catch (reason) { setError(String(reason)); return null; }
    finally { locked.current = false; setBusy(false); }
  };
  const bridge = () => {
    if (!api.current) throw Error('Ponte nativa indisponível.');
    return api.current;
  };
  return { state, error, busy,
    start: (settings: AliceSettings) => run(async () => { await bridge().StartAliceSession(JSON.stringify(settings)); return true; }),
    stop: () => run(async () => { await bridge().StopAliceSession(); return true; }),
    pick: (kind: string) => run(() => bridge().PickAlicePath(kind)),
    perceive: (modality: AliceModality, path: string) => run(async () => JSON.parse(await bridge().PerceiveAliceFile(modality, path)) as AliceFrame),
    perceivePair: (image: string, audio: string) => run(async () => JSON.parse(await bridge().PerceiveAlicePair(image, audio)) as AliceFrame),
    perceiveWordAudio: (path: string, word: string) => run(async () => JSON.parse(await bridge().PerceiveAliceWordAudio(path, word)) as AliceFrame),
    perceiveText: (text: string) => run(async () => JSON.parse(await bridge().PerceiveAliceText(text)) as AliceFrame),
    send: (kind: AliceAction, payload: object) => run(async () => JSON.parse(await bridge().SendAliceMessage(JSON.stringify({ kind, payload }))) as { id: string }),
  };
}
